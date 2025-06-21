import React from 'react';

/**
 * Simple markdown formatter for our specific use case
 * Handles: **bold text**, newlines, and basic formatting
 */
export function formatMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];

  lines.forEach((line, lineIndex) => {
    if (line.trim() === '') {
      // Empty line - add space
      elements.push(<br key={`br-${lineIndex}`} />);
      return;
    }

    // Process bold text **text**
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    const lineElements: React.ReactNode[] = [];

    parts.forEach((part, partIndex) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        // Bold text
        const boldText = part.slice(2, -2);
        lineElements.push(
          <strong key={`bold-${lineIndex}-${partIndex}`} className="font-semibold text-gray-900">
            {boldText}
          </strong>
        );
      } else if (part.trim()) {
        // Regular text
        lineElements.push(
          <span key={`text-${lineIndex}-${partIndex}`}>
            {part}
          </span>
        );
      }
    });

    // Wrap the line in appropriate element
    if (line.startsWith('# ')) {
      // Header
      elements.push(
        <h3 key={`h3-${lineIndex}`} className="text-lg font-semibold text-gray-800 mt-4 mb-2">
          {lineElements}
        </h3>
      );
    } else if (line.startsWith('## ')) {
      // Subheader
      elements.push(
        <h4 key={`h4-${lineIndex}`} className="text-md font-semibold text-gray-700 mt-3 mb-1">
          {lineElements}
        </h4>
      );
    } else if (line.startsWith('- ')) {
      // List item
      elements.push(
        <div key={`li-${lineIndex}`} className="ml-4 mb-1">
          <span className="text-gray-600 mr-2">•</span>
          {lineElements}
        </div>
      );
    } else {
      // Regular paragraph
      elements.push(
        <p key={`p-${lineIndex}`} className="mb-2">
          {lineElements}
        </p>
      );
    }
  });

  return elements;
}