"use client";

import { useParams } from "next/navigation";
import { ChatExperience } from "@/components/chat/ChatExperience";

export default function ChatByIdPage() {
  const params = useParams();
  const id = typeof params.conversationId === "string" ? params.conversationId : "";
  return <ChatExperience conversationIdFromUrl={id || null} />;
}
