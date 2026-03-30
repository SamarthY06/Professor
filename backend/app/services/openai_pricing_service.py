"""
OpenAI Pricing Service - Fetches and syncs model pricing from OpenAI.

This service:
1. Fetches current pricing from OpenAI's API
2. Syncs pricing to our database
3. Detects new models and price changes
4. Provides fallback pricing if API is unavailable
"""

import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.models.usage import ModelPricing

logger = get_logger(__name__)


# Fallback pricing in case OpenAI API is unavailable
# Prices in cents per 1M tokens (updated Jan 2026)
FALLBACK_PRICING = {
    # GPT-4.1 family (latest, better than 4o for cost/speed)
    "gpt-4.1": {
        "display_name": "GPT-4.1",
        "input": 200,  # $2.00/1M
        "output": 800,  # $8.00/1M
        "cached_input": 50,  # $0.50/1M
        "description": "Latest GPT-4 - better cost/speed than 4o",
        "max_context": 1047576,  # 1M context
        "supports_batch": True,
        "available_for_free": False,
    },
    "gpt-4.1-mini": {
        "display_name": "GPT-4.1 Mini",
        "input": 40,  # $0.40/1M
        "output": 160,  # $1.60/1M
        "cached_input": 10,  # $0.10/1M
        "description": "Fast, affordable GPT-4.1 variant",
        "max_context": 1047576,  # 1M context
        "supports_batch": True,
        "available_for_free": True,
    },
    "gpt-4.1-nano": {
        "display_name": "GPT-4.1 Nano",
        "input": 10,  # $0.10/1M
        "output": 40,  # $0.40/1M
        "cached_input": 3,  # $0.025/1M
        "description": "Fastest, cheapest GPT-4.1 for simple tasks",
        "max_context": 1047576,  # 1M context
        "supports_batch": True,
        "available_for_free": True,
    },
    # GPT-4o family
    "gpt-4o": {
        "display_name": "GPT-4o",
        "input": 250,  # $2.50/1M
        "output": 1000,  # $10.00/1M
        "cached_input": 125,  # $1.25/1M
        "description": "Multimodal model for complex tasks",
        "max_context": 128000,
        "supports_batch": True,
        "available_for_free": False,
    },
    "gpt-4o-mini": {
        "display_name": "GPT-4o Mini",
        "input": 15,  # $0.15/1M
        "output": 60,  # $0.60/1M
        "cached_input": 8,  # $0.075/1M
        "description": "Fast and affordable for simple tasks",
        "max_context": 128000,
        "supports_batch": True,
        "available_for_free": True,
    },
    # GPT-5 family (based on your screenshot)
    "gpt-5.2": {
        "display_name": "GPT-5.2",
        "input": 175,  # $1.75/1M
        "output": 1400,  # $14.00/1M
        "cached_input": 18,  # $0.175/1M
        "description": "Best model for coding and agentic tasks",
        "max_context": 200000,
        "supports_batch": True,
        "available_for_free": False,
    },
    "gpt-5.2-pro": {
        "display_name": "GPT-5.2 Pro",
        "input": 2100,  # $21.00/1M
        "output": 16800,  # $168.00/1M
        "cached_input": None,
        "description": "Smartest and most precise model",
        "max_context": 200000,
        "supports_batch": False,
        "available_for_free": False,
    },
    "gpt-5-mini": {
        "display_name": "GPT-5 Mini",
        "input": 25,  # $0.25/1M
        "output": 200,  # $2.00/1M
        "cached_input": 3,  # $0.025/1M
        "description": "Faster, cheaper version of GPT-5",
        "max_context": 200000,
        "supports_batch": True,
        "available_for_free": True,
    },
    # Embedding models
    "text-embedding-3-small": {
        "display_name": "Embedding Small",
        "input": 2,  # $0.02/1M
        "output": 0,
        "cached_input": None,
        "description": "Efficient embeddings for RAG",
        "max_context": 8191,
        "supports_batch": True,
        "available_for_free": True,
    },
    "text-embedding-3-large": {
        "display_name": "Embedding Large",
        "input": 13,  # $0.13/1M
        "output": 0,
        "cached_input": None,
        "description": "High quality embeddings",
        "max_context": 8191,
        "supports_batch": True,
        "available_for_free": False,
    },
    # O1 reasoning models
    "o1": {
        "display_name": "O1",
        "input": 1500,  # $15.00/1M
        "output": 6000,  # $60.00/1M
        "cached_input": 750,  # $7.50/1M
        "description": "Advanced reasoning model",
        "max_context": 200000,
        "supports_batch": False,
        "available_for_free": False,
    },
    "o1-mini": {
        "display_name": "O1 Mini",
        "input": 110,  # $1.10/1M
        "output": 440,  # $4.40/1M
        "cached_input": 55,  # $0.55/1M
        "description": "Smaller reasoning model",
        "max_context": 128000,
        "supports_batch": True,
        "available_for_free": False,
    },
    "o3-mini": {
        "display_name": "O3 Mini",
        "input": 110,  # $1.10/1M
        "output": 440,  # $4.40/1M
        "cached_input": 55,  # $0.55/1M
        "description": "Latest compact reasoning model",
        "max_context": 200000,
        "supports_batch": True,
        "available_for_free": False,
    },
}


class OpenAIPricingService:
    """
    Service for fetching and managing OpenAI model pricing.
    
    Features:
    - Fetch pricing from OpenAI API (when available)
    - Fallback to hardcoded pricing
    - Sync pricing to database
    - Detect price changes and new models
    """
    
    OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def fetch_models_from_openai(self) -> Optional[List[Dict]]:
        """
        Fetch available models from OpenAI API.
        
        Note: OpenAI doesn't expose pricing via API, so we use this
        to discover new models and then apply our pricing config.
        """
        if not settings.openai_api_key:
            logger.warning("openai_api_key_not_set", action="skipping_model_fetch")
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.OPENAI_MODELS_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    
                    # Filter to relevant models (GPT, embedding, o1, etc.)
                    relevant_models = [
                        m for m in models
                        if any(prefix in m.get("id", "").lower() 
                               for prefix in ["gpt-", "text-embedding", "o1", "o3"])
                    ]
                    
                    logger.info(
                        "openai_models_fetched",
                        total_models=len(models),
                        relevant_models=len(relevant_models),
                    )
                    return relevant_models
                else:
                    logger.warning(
                        "openai_models_fetch_failed",
                        status_code=response.status_code,
                    )
                    return None
                    
        except Exception as e:
            logger.exception("openai_models_fetch_error", error=str(e))
            return None
    
    async def sync_pricing_to_database(self) -> Dict:
        """
        Sync model pricing to database.
        
        Returns summary of changes made.
        """
        changes = {
            "added": [],
            "updated": [],
            "unchanged": [],
            "errors": [],
        }
        
        # Get current pricing from database
        result = await self.db.execute(select(ModelPricing))
        existing_models = {m.model_name: m for m in result.scalars().all()}
        
        # Try to fetch models from OpenAI to discover new ones
        openai_models = await self.fetch_models_from_openai()
        
        # Merge OpenAI models with our fallback pricing
        all_model_names = set(FALLBACK_PRICING.keys())
        if openai_models:
            for model in openai_models:
                model_id = model.get("id", "")
                # Normalize model name
                if model_id and model_id not in all_model_names:
                    # Check if it's a variant we should track
                    for known_prefix in ["gpt-4o", "gpt-5", "o1", "o3", "text-embedding"]:
                        if model_id.startswith(known_prefix):
                            all_model_names.add(model_id)
                            break
        
        # Update or create pricing for each model
        for model_name in all_model_names:
            try:
                pricing_config = FALLBACK_PRICING.get(model_name)
                
                if not pricing_config:
                    # New model discovered from OpenAI - use default pricing
                    # This is a signal to admin to update pricing
                    pricing_config = {
                        "display_name": model_name.replace("-", " ").title(),
                        "input": 100,  # Default $1/1M
                        "output": 400,  # Default $4/1M
                        "cached_input": 50,
                        "description": f"New model - pricing needs review",
                        "max_context": 128000,
                        "supports_batch": False,
                        "available_for_free": False,
                    }
                    logger.warning(
                        "new_model_discovered",
                        model_name=model_name,
                        action="using_default_pricing",
                    )
                
                if model_name in existing_models:
                    # Check if pricing changed
                    existing = existing_models[model_name]
                    needs_update = (
                        existing.input_price_per_million != pricing_config["input"] or
                        existing.output_price_per_million != pricing_config["output"] or
                        existing.cached_input_price_per_million != pricing_config.get("cached_input")
                    )
                    
                    if needs_update:
                        await self.db.execute(
                            update(ModelPricing)
                            .where(ModelPricing.model_name == model_name)
                            .values(
                                input_price_per_million=pricing_config["input"],
                                output_price_per_million=pricing_config["output"],
                                cached_input_price_per_million=pricing_config.get("cached_input"),
                                description=pricing_config.get("description"),
                                max_context_tokens=pricing_config.get("max_context", 128000),
                                supports_batch=pricing_config.get("supports_batch", False),
                                available_for_free=pricing_config.get("available_for_free", False),
                                updated_at=datetime.utcnow(),
                            )
                        )
                        changes["updated"].append(model_name)
                        logger.info(
                            "model_pricing_updated",
                            model_name=model_name,
                            old_input=existing.input_price_per_million,
                            new_input=pricing_config["input"],
                        )
                    else:
                        changes["unchanged"].append(model_name)
                else:
                    # New model - add to database
                    new_model = ModelPricing(
                        model_name=model_name,
                        display_name=pricing_config["display_name"],
                        input_price_per_million=pricing_config["input"],
                        output_price_per_million=pricing_config["output"],
                        cached_input_price_per_million=pricing_config.get("cached_input"),
                        is_available=True,
                        supports_batch=pricing_config.get("supports_batch", False),
                        max_context_tokens=pricing_config.get("max_context", 128000),
                        available_for_free=pricing_config.get("available_for_free", False),
                        available_for_byok=True,
                        description=pricing_config.get("description"),
                    )
                    self.db.add(new_model)
                    changes["added"].append(model_name)
                    logger.info("model_pricing_added", model_name=model_name)
                    
            except Exception as e:
                changes["errors"].append({"model": model_name, "error": str(e)})
                logger.exception("model_pricing_sync_error", model_name=model_name, error=str(e))
        
        await self.db.commit()
        
        logger.info(
            "pricing_sync_completed",
            added=len(changes["added"]),
            updated=len(changes["updated"]),
            unchanged=len(changes["unchanged"]),
            errors=len(changes["errors"]),
        )
        
        return changes
    
    async def get_model_pricing(self, model_name: str) -> Optional[Dict]:
        """Get pricing for a specific model."""
        result = await self.db.execute(
            select(ModelPricing).where(ModelPricing.model_name == model_name)
        )
        model = result.scalar_one_or_none()
        
        if model:
            return {
                "model_name": model.model_name,
                "display_name": model.display_name,
                "input_price_per_million": model.input_price_per_million,
                "output_price_per_million": model.output_price_per_million,
                "cached_input_price_per_million": model.cached_input_price_per_million,
                "is_available": model.is_available,
                "supports_batch": model.supports_batch,
                "available_for_free": model.available_for_free,
            }
        
        # Fallback to hardcoded pricing
        if model_name in FALLBACK_PRICING:
            config = FALLBACK_PRICING[model_name]
            return {
                "model_name": model_name,
                "display_name": config["display_name"],
                "input_price_per_million": config["input"],
                "output_price_per_million": config["output"],
                "cached_input_price_per_million": config.get("cached_input"),
                "is_available": True,
                "supports_batch": config.get("supports_batch", False),
                "available_for_free": config.get("available_for_free", False),
            }
        
        return None
    
    async def calculate_cost(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> int:
        """
        Calculate cost in cents for a given usage.
        
        Returns cost in cents (integer for precision).
        """
        pricing = await self.get_model_pricing(model_name)
        
        if not pricing:
            logger.warning("pricing_not_found", model_name=model_name)
            return 0
        
        # Calculate cost (prices are per million tokens)
        regular_input_tokens = input_tokens - cached_tokens
        
        input_cost = (regular_input_tokens / 1_000_000) * pricing["input_price_per_million"]
        output_cost = (output_tokens / 1_000_000) * pricing["output_price_per_million"]
        
        cached_cost = 0
        if cached_tokens > 0 and pricing.get("cached_input_price_per_million"):
            cached_cost = (cached_tokens / 1_000_000) * pricing["cached_input_price_per_million"]
        
        total_cents = int(round(input_cost + output_cost + cached_cost))
        return total_cents


async def sync_openai_pricing(db: AsyncSession) -> Dict:
    """
    Standalone function to sync OpenAI pricing.
    Called by Temporal worker.
    """
    service = OpenAIPricingService(db)
    return await service.sync_pricing_to_database()
