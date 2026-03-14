import Link from "next/link";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";

export default function Home() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-16 flex flex-col items-center gap-10">
      <div className="text-center space-y-2">
        <h1 className="text-4xl font-bold tracking-tight">WrenchAI</h1>
        <p className="text-muted-foreground">
          Your AI-powered vehicle manual assistant — Tata Tiago Edition
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 w-full max-w-lg">
        <Link href="/ask" className="block">
          <Card className="h-full hover:border-primary/50 transition-colors cursor-pointer">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl">Ask Questions</CardTitle>
              <CardDescription>
                Chat-style Q&amp;A about your vehicle manual
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/guide" className="block">
          <Card className="h-full hover:border-primary/50 transition-colors cursor-pointer">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl">Guide Me</CardTitle>
              <CardDescription>
                Step-by-step voice-guided walkthrough
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>
      </div>
    </div>
  );
}
