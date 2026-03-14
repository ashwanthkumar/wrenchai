"use client";

import type { ManualAnswer } from "@/lib/api";

interface AnswerDisplayProps {
  answer: ManualAnswer;
}

export function AnswerDisplay({ answer }: AnswerDisplayProps) {
  return (
    <div className="space-y-4">
      <p className="text-base leading-relaxed">{answer.summary}</p>

      {answer.steps.length > 0 && (
        <ol className="list-decimal list-inside space-y-1.5 text-sm">
          {answer.steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      )}

      {answer.pages_referenced.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-2 border-t">
          <span className="text-xs text-muted-foreground">Pages:</span>
          {answer.pages_referenced.map((page, i) => (
            <span
              key={i}
              className="text-xs bg-muted px-2 py-0.5 rounded-full"
            >
              {page}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
