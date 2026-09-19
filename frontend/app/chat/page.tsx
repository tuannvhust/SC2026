"use client";

import React, { useState } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { ChatHeader } from '@/components/ChatHeader';
import { MessageBubble } from '@/components/MessageBubble';
import { TypingIndicator } from '@/components/TypingIndicator';
import { FloatingInput } from '@/components/FloatingInput';
import { Message } from '@/types'; // we'll create a simple type file or define inline

export default function ChatPage() {
  const [messages, setMessages] = useState<Array<Message>>([]);
  const [loading, setLoading] = useState(false);
  const [lastUserMessage, setLastUserMessage] = useState('');
  const [toast, setToast] = useState('');

  const sendMessage = async (text: string) => {
    if (!text.trim()) return;
    const userMsg = text.trim();
    setLastUserMessage(userMsg);
    setMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setLoading(true);
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: 'anonymous', message: userMsg }),
      });
      const data = await res.json();
      const reply = data.reply ?? 'Không có phản hồi.';
      setMessages(prev => [...prev, { role: 'assistant', text: reply }]);
    } catch (e) {
      console.error(e);
      setMessages(prev => [...prev, { role: 'assistant', text: 'Lỗi khi gọi API.' }]);
    } finally {
      setLoading(false);
    }
  };

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 2000);
  };

  const retryLastMessage = () => {
    if (lastUserMessage && !loading) void sendMessage(lastUserMessage);
  };

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      {/* Sidebar */}
      <Sidebar />
      {/* Main chat area */}
      <main className="relative flex min-h-screen flex-1 flex-col px-4 pb-32 pt-4 md:px-10">
        <ChatHeader />
        <div className="mx-auto mb-4 flex w-full max-w-3xl flex-1 flex-col overflow-y-auto pb-28">
          {messages.map((msg, idx) => (
            <MessageBubble
              key={idx}
              msg={msg}
              onCopy={() => showToast('Đã sao chép tin nhắn')}
              onRefresh={retryLastMessage}
            />
          ))}
          {loading && <TypingIndicator />}
        </div>
        <FloatingInput onSend={sendMessage} loading={loading} />
      </main>
      {toast && (
        <div role="status" className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-slate-900 px-4 py-2 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
