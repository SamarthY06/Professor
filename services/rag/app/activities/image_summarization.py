"""Image summarization activities using OpenAI Vision."""
import base64
from typing import Optional

from openai import OpenAI
from temporalio import activity

from app.config.settings import settings
from app.config.logging import get_logger
from app.activities.cost_tracking import record_cost_sync

logger = get_logger(__name__)

IMAGE_SUMMARY_PROMPT = """You are analyzing an image from a technical textbook or manual.

Your task:
1. Describe what the image shows in 1-3 concise sentences
2. Focus on the educational/learning value of the image
3. Include any labels, equations, or key concepts visible
4. If it's a diagram, explain what it illustrates
5. If it's a graph/chart, describe the data relationship

Keep the summary concise but informative for someone studying this material.
Do NOT start with "This image shows" - be direct.
"""


@activity.defn
async def summarize_image(
    image_data: str,
    image_ext: str,
    page_number: int,
    context: Optional[str] = None,
    document_id: Optional[str] = None,
) -> str:
    """
    Generate a learning-focused summary of an image using OpenAI Vision.

    Args:
        image_data: Base64 encoded image data
        image_ext: Image extension (png, jpg, etc.)
        page_number: Page number where image appears
        context: Optional surrounding text context
        document_id: Optional document ID for cost tracking

    Returns:
        Image summary text
    """
    activity.logger.info(f"Summarizing image from page {page_number}")

    client = OpenAI(api_key=settings.openai_api_key)

    # Determine media type
    media_type = f"image/{image_ext}"
    if image_ext == "jpg":
        media_type = "image/jpeg"

    # Build prompt with context if available
    prompt = IMAGE_SUMMARY_PROMPT
    if context:
        prompt += f"\n\nSurrounding text context:\n{context[:500]}"

    try:
        response = client.chat.completions.create(
            model=settings.openai_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}",
                                "detail": "low",  # Use low detail to reduce tokens
                            },
                        },
                    ],
                }
            ],
            max_tokens=300,
            temperature=0.3,
        )

        # Track cost
        if response.usage:
            try:
                await record_cost_sync(
                    cost_type="IMAGE_SUMMARY",
                    model=settings.openai_vision_model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    document_id=document_id,
                    description=f"Image summary for page {page_number}",
                )
            except Exception as e:
                activity.logger.warning(f"Failed to record cost: {e}")

        summary = response.choices[0].message.content or "Image content could not be summarized."

        activity.logger.info(f"Generated summary: {len(summary)} characters")
        return summary.strip()

    except Exception as e:
        activity.logger.error(f"Failed to summarize image: {e}")
        return f"[Image on page {page_number} - summary unavailable]"


@activity.defn
async def summarize_images_batch(
    images: list[dict],
    surrounding_text: Optional[dict[int, str]] = None,
    document_id: Optional[str] = None,
) -> list[dict]:
    """
    Summarize multiple images in batch.

    Args:
        images: List of image dictionaries with image_data, ext, page_number
        surrounding_text: Optional dict mapping page numbers to context text
        document_id: Optional document ID for cost tracking

    Returns:
        List of image summaries with metadata
    """
    activity.logger.info(f"Summarizing batch of {len(images)} images")

    summaries = []
    client = OpenAI(api_key=settings.openai_api_key)
    total_input_tokens = 0
    total_output_tokens = 0

    for img in images:
        page_number = img["page_number"]
        context = surrounding_text.get(page_number) if surrounding_text else None

        # Determine media type
        image_ext = img.get("ext", "png")
        media_type = f"image/{image_ext}"
        if image_ext == "jpg":
            media_type = "image/jpeg"

        prompt = IMAGE_SUMMARY_PROMPT
        if context:
            prompt += f"\n\nSurrounding text context:\n{context[:500]}"

        try:
            response = client.chat.completions.create(
                model=settings.openai_vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{img['image_data']}",
                                    "detail": "low",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=300,
                temperature=0.3,
            )

            # Accumulate token usage
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens
                total_output_tokens += response.usage.completion_tokens

            summary = response.choices[0].message.content or "Image content could not be summarized."

            summaries.append({
                "page_number": page_number,
                "image_index": img.get("image_index", 0),
                "summary": summary.strip(),
                "bbox": img.get("bbox"),
            })

        except Exception as e:
            activity.logger.error(f"Failed to summarize image on page {page_number}: {e}")
            summaries.append({
                "page_number": page_number,
                "image_index": img.get("image_index", 0),
                "summary": f"[Image on page {page_number} - summary unavailable]",
                "bbox": img.get("bbox"),
            })

    # Record aggregated cost for batch
    if total_input_tokens > 0 or total_output_tokens > 0:
        try:
            await record_cost_sync(
                cost_type="IMAGE_SUMMARY",
                model=settings.openai_vision_model,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                document_id=document_id,
                description=f"Batch image summary for {len(images)} images",
                metadata={"image_count": len(images)},
            )
        except Exception as e:
            activity.logger.warning(f"Failed to record cost: {e}")

    activity.logger.info(f"Completed {len(summaries)} image summaries")
    return summaries
