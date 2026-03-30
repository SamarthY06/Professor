'use client';

import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';

// KaTeX CSS is imported in globals.css

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Preprocess content to convert various LaTeX delimiters to standard format.
 * - \[...\] → $$...$$ (block math)
 * - \(...\) → $...$ (inline math)
 * - Also handles escaped brackets that might appear in LLM output
 */
function preprocessMath(content: string): string {
  if (!content) return '';
  
  let processed = content;
  
  // Convert \[...\] to $$...$$ for block math
  // Handle both single-line and multi-line
  processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => {
    return `$$${math.trim()}$$`;
  });
  
  // Convert \(...\) to $...$ for inline math
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => {
    return `$${math.trim()}$`;
  });
  
  // Handle cases where [ and ] are used without backslashes for display math
  // Only if they appear to contain LaTeX commands
  processed = processed.replace(/\[\s*(\\[a-zA-Z]+[\s\S]*?)\s*\]/g, (match, math) => {
    // Check if it looks like LaTeX (contains backslash commands)
    if (math.includes('\\') && !match.startsWith('$$')) {
      return `$$${math.trim()}$$`;
    }
    return match;
  });
  
  return processed;
}

/**
 * MarkdownRenderer - Renders markdown content with full support for:
 * - LaTeX math formulas (inline $...$ and block $$...$$)
 * - Code blocks with syntax highlighting
 * - Tables (GitHub Flavored Markdown)
 * - All standard markdown (bold, italic, lists, headers, links, etc.)
 * 
 * This is a pure client-side renderer - no API calls needed.
 * Similar to how ChatGPT renders its responses.
 */
export function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  // Preprocess content to normalize math delimiters
  const processedContent = useMemo(() => preprocessMath(content), [content]);
  
  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={{
          // Custom styling for code blocks
          code({ node, inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            
            if (inline) {
              return (
                <code
                  className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-sm font-mono text-pink-600 dark:text-pink-400"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            
            return (
              <div className="relative my-4">
                {language && (
                  <div className="absolute top-0 right-0 px-2 py-1 text-xs text-gray-500 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 rounded-bl font-mono">
                    {language}
                  </div>
                )}
                <pre className="overflow-x-auto rounded-lg bg-gray-900 dark:bg-gray-950 p-4 text-sm">
                  <code className={`${className || ''} text-gray-100`} {...props}>
                    {children}
                  </code>
                </pre>
              </div>
            );
          },
          
          // Custom styling for tables
          table({ children, ...props }: any) {
            return (
              <div className="overflow-x-auto my-4">
                <table className="min-w-full border-collapse border border-gray-200 dark:border-gray-700 rounded-lg" {...props}>
                  {children}
                </table>
              </div>
            );
          },
          
          thead({ children, ...props }: any) {
            return (
              <thead className="bg-gray-50 dark:bg-gray-800" {...props}>
                {children}
              </thead>
            );
          },
          
          th({ children, ...props }: any) {
            return (
              <th className="px-4 py-2 text-left text-sm font-semibold text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-700" {...props}>
                {children}
              </th>
            );
          },
          
          td({ children, ...props }: any) {
            return (
              <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700" {...props}>
                {children}
              </td>
            );
          },
          
          // Custom styling for blockquotes
          blockquote({ children, ...props }: any) {
            return (
              <blockquote
                className="border-l-4 border-blue-500 pl-4 my-4 italic text-gray-600 dark:text-gray-300 bg-blue-50 dark:bg-blue-900/20 py-2 rounded-r"
                {...props}
              >
                {children}
              </blockquote>
            );
          },
          
          // Custom styling for links
          a({ children, href, ...props }: any) {
            return (
              <a
                href={href}
                className="text-blue-600 dark:text-blue-400 hover:underline"
                target="_blank"
                rel="noopener noreferrer"
                {...props}
              >
                {children}
              </a>
            );
          },
          
          // Custom styling for lists
          ul({ children, ...props }: any) {
            return (
              <ul className="list-disc list-inside my-2 space-y-1" {...props}>
                {children}
              </ul>
            );
          },
          
          ol({ children, ...props }: any) {
            return (
              <ol className="list-decimal list-inside my-2 space-y-1" {...props}>
                {children}
              </ol>
            );
          },
          
          li({ children, ...props }: any) {
            return (
              <li className="text-gray-700 dark:text-gray-200" {...props}>
                {children}
              </li>
            );
          },
          
          // Custom styling for headings
          h1({ children, ...props }: any) {
            return (
              <h1 className="text-2xl font-bold mt-6 mb-3 text-gray-900 dark:text-gray-100" {...props}>
                {children}
              </h1>
            );
          },
          
          h2({ children, ...props }: any) {
            return (
              <h2 className="text-xl font-bold mt-5 mb-2 text-gray-900 dark:text-gray-100" {...props}>
                {children}
              </h2>
            );
          },
          
          h3({ children, ...props }: any) {
            return (
              <h3 className="text-lg font-semibold mt-4 mb-2 text-gray-900 dark:text-gray-100" {...props}>
                {children}
              </h3>
            );
          },
          
          h4({ children, ...props }: any) {
            return (
              <h4 className="text-base font-semibold mt-3 mb-1 text-gray-900 dark:text-gray-100" {...props}>
                {children}
              </h4>
            );
          },
          
          // Custom styling for paragraphs
          p({ children, ...props }: any) {
            return (
              <p className="my-2 leading-relaxed text-gray-700 dark:text-gray-200" {...props}>
                {children}
              </p>
            );
          },
          
          // Custom styling for horizontal rules
          hr({ ...props }: any) {
            return (
              <hr className="my-6 border-gray-200 dark:border-gray-700" {...props} />
            );
          },
          
          // Custom styling for images
          img({ src, alt, ...props }: any) {
            return (
              <img
                src={src}
                alt={alt || ''}
                className="max-w-full h-auto rounded-lg my-4"
                {...props}
              />
            );
          },
          
          // Strong/bold text
          strong({ children, ...props }: any) {
            return (
              <strong className="font-semibold text-gray-900 dark:text-gray-100" {...props}>
                {children}
              </strong>
            );
          },
          
          // Emphasis/italic text
          em({ children, ...props }: any) {
            return (
              <em className="italic" {...props}>
                {children}
              </em>
            );
          },
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownRenderer;
