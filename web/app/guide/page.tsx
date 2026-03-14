"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { QuestionForm } from "@/components/question-form";
import { AnswerDisplay } from "@/components/answer-display";
import { Button } from "@/components/ui/button";
import { queryManual, type ManualAnswer } from "@/lib/api";

function speak(text: string) {
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  window.speechSynthesis.speak(utt);
}

export default function GuidePage() {
  const [answer, setAnswer] = useState<ManualAnswer | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null);
  const [currentImagePreviews, setCurrentImagePreviews] = useState<string[]>([]);
  const [stepIndex, setStepIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guidingRef = useRef(false);

  const totalSteps = answer?.steps.length ?? 0;

  // Speak current step whenever stepIndex changes in guided mode
  useEffect(() => {
    if (!answer || !guidingRef.current) return;
    if (answer.steps.length === 0) return;
    speak(`Step ${stepIndex + 1}. ${answer.steps[stepIndex]}`);
  }, [stepIndex, answer]);

  // Cleanup speech on unmount
  useEffect(() => {
    return () => window.speechSynthesis.cancel();
  }, []);

  async function handleSubmit(question: string, images: File[]) {
    setCurrentQuestion(question);
    setCurrentImagePreviews(images.map((f) => URL.createObjectURL(f)));
    setLoading(true);
    setError(null);
    try {
      const result = await queryManual(question, images);
      setAnswer(result);
      setStepIndex(0);
      guidingRef.current = true;
      // Read summary first, then first step
      if (result.steps.length > 0) {
        speak(result.summary + ". Let's begin. Step 1. " + result.steps[0]);
      } else {
        speak(result.summary);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const next = useCallback(() => {
    if (stepIndex < totalSteps - 1) setStepIndex((i) => i + 1);
  }, [stepIndex, totalSteps]);

  const prev = useCallback(() => {
    if (stepIndex > 0) setStepIndex((i) => i - 1);
  }, [stepIndex]);

  const repeat = useCallback(() => {
    if (answer && answer.steps.length > 0) {
      speak(`Step ${stepIndex + 1}. ${answer.steps[stepIndex]}`);
    }
  }, [answer, stepIndex]);

  const reset = useCallback(() => {
    window.speechSynthesis.cancel();
    guidingRef.current = false;
    setAnswer(null);
    setCurrentQuestion(null);
    setCurrentImagePreviews([]);
    setStepIndex(0);
  }, []);

  // Question input mode
  if (!answer) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <h2 className="text-2xl font-semibold">Guide Me</h2>
        <p className="text-muted-foreground">
          Ask a question and I&apos;ll walk you through the answer step by step
          with voice guidance.
        </p>

        {currentQuestion && (
          <div className="bg-muted rounded-lg p-4">
            <p className="font-medium">{currentQuestion}</p>
            {currentImagePreviews.length > 0 && (
              <div className="flex gap-2 mt-2">
                {currentImagePreviews.map((src, j) => (
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
        )}

        {error && (
          <div className="text-center py-4 text-destructive">{error}</div>
        )}

        {loading ? (
          <div className="py-4 text-muted-foreground animate-pulse text-sm">
            Searching the manual...
          </div>
        ) : (
          <QuestionForm onSubmit={handleSubmit} loading={loading} />
        )}
      </div>
    );
  }

  const done = stepIndex >= totalSteps - 1;

  // Guided mode
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold">Guide Me</h2>
        <Button variant="outline" size="sm" onClick={reset}>
          New Question
        </Button>
      </div>

      {/* Question */}
      {currentQuestion && (
        <div className="bg-muted rounded-lg p-4">
          <p className="font-medium">{currentQuestion}</p>
          {currentImagePreviews.length > 0 && (
            <div className="flex gap-2 mt-2">
              {currentImagePreviews.map((src, j) => (
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
      )}

      {/* Summary */}
      <div className="bg-card border rounded-lg p-4">
        <p className="text-sm font-medium text-muted-foreground mb-1">
          Summary
        </p>
        <p>{answer.summary}</p>
      </div>

      {/* Step display */}
      {totalSteps > 0 && (
        <div className="space-y-4">
          <div className="text-center text-sm text-muted-foreground">
            Step {stepIndex + 1} of {totalSteps}
          </div>

          {/* Progress bar */}
          <div className="w-full bg-muted rounded-full h-1.5">
            <div
              className="bg-primary h-1.5 rounded-full transition-all"
              style={{
                width: `${((stepIndex + 1) / totalSteps) * 100}%`,
              }}
            />
          </div>

          {/* Current step */}
          <div className="bg-card border rounded-lg p-6 text-center">
            <p className="text-xl leading-relaxed">{answer.steps[stepIndex]}</p>
          </div>

          {/* Controls */}
          <div className="flex justify-center gap-3">
            <Button
              variant="outline"
              onClick={prev}
              disabled={stepIndex === 0}
            >
              Previous
            </Button>
            <Button variant="outline" onClick={repeat}>
              Repeat
            </Button>
            {done ? (
              <Button onClick={reset}>Done</Button>
            ) : (
              <Button onClick={next}>Next</Button>
            )}
          </div>
        </div>
      )}

      {/* Pages referenced (shown when done or if no steps) */}
      {(done || totalSteps === 0) &&
        answer.pages_referenced.length > 0 && (
          <div className="pt-4">
            <AnswerDisplay answer={answer} />
          </div>
        )}
    </div>
  );
}
