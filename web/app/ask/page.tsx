"use client";

import { useState } from "react";
import { QuestionForm } from "@/components/question-form";
import { AnswerDisplay } from "@/components/answer-display";
import { queryManual, type ManualAnswer } from "@/lib/api";

interface Exchange {
  question: string;
  imagePreviews: string[];
  answer: ManualAnswer | null;
  error?: string;
}

export default function AskPage() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(question: string, images: File[]) {
    const previews = images.map((f) => URL.createObjectURL(f));
    const idx = exchanges.length;

    // Immediately append the question with no answer yet
    setExchanges((prev) => [
      ...prev,
      { question, imagePreviews: previews, answer: null },
    ]);
    setLoading(true);

    try {
      const answer = await queryManual(question, images);
      setExchanges((prev) =>
        prev.map((ex, i) => (i === idx ? { ...ex, answer } : ex))
      );
    } catch (err) {
      setExchanges((prev) =>
        prev.map((ex, i) =>
          i === idx
            ? {
                ...ex,
                error:
                  err instanceof Error ? err.message : "Something went wrong",
              }
            : ex
        )
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <h2 className="text-2xl font-semibold">Ask Questions</h2>

      <div className="space-y-6">
        {exchanges.map((ex, i) => (
          <div key={i} className="space-y-3">
            <div className="bg-muted rounded-lg p-4">
              <p className="font-medium">{ex.question}</p>
              {ex.imagePreviews.length > 0 && (
                <div className="flex gap-2 mt-2">
                  {ex.imagePreviews.map((src, j) => (
                    <img
                      key={j}
                      src={src}
                      alt="uploaded"
                      className="h-16 w-16 object-cover rounded"
                    />
                  ))}
                </div>
              )}
            </div>

            {ex.answer ? (
              <div className="bg-card border rounded-lg p-4">
                <AnswerDisplay answer={ex.answer} />
              </div>
            ) : ex.error ? (
              <div className="text-destructive text-sm py-2">{ex.error}</div>
            ) : (
              <div className="py-4 text-muted-foreground animate-pulse text-sm">
                Searching the manual...
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="sticky bottom-0 bg-background pt-4 pb-2 border-t">
        <QuestionForm onSubmit={handleSubmit} loading={loading} />
      </div>
    </div>
  );
}
