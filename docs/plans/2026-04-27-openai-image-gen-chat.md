# OpenAI Image Gen Chat Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a standalone, chat-like product that uses the OpenAI image generation pipeline from the backend.

**Architecture:** A standalone React/Vite application located in `apps/openai-image-gen`. It will communicate with the existing FastAPI backend OpenAI endpoints. The UI will feature a conversation history where each message results in a set of generated images.

**Tech Stack:** React 18, TypeScript, Vite, TailwindCSS, Lucide React (icons), Axios/Fetch for API.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `apps/openai-image-gen/` (scaffolded via Vite)
- Modify: `package.json` (root) to include the new app in workspaces (if using workspaces) - *Decision: The user asked for "Completely Independent", so we won't strictly enforce root workspace unless necessary, but we'll create the folder.*

**Step 1: Scaffold Vite Project**
Run: `mkdir -p apps && cd apps && npm create vite@latest openai-image-gen -- --template react-ts`

**Step 2: Install Dependencies**
Run: `cd apps/openai-image-gen && npm install && npm install tailwindcss postcss autoprefixer lucide-react axios`

**Step 3: Initialize Tailwind**
Run: `cd apps/openai-image-gen && npx tailwindcss init -p`

**Step 4: Configure Tailwind**
Modify `apps/openai-image-gen/tailwind.config.js` to include the correct paths.

**Step 5: Verify Scaffolding**
Run: `cd apps/openai-image-gen && npm run build`
Expected: Success.

---

### Task 2: Core Chat UI Components

**Files:**
- Create: `apps/openai-image-gen/src/components/ChatWindow.tsx`
- Create: `apps/openai-image-gen/src/components/Message.tsx`
- Create: `apps/openai-image-gen/src/components/InputBar.tsx`

**Step 1: Implement ChatWindow**
Create the main container with a scrollable area for messages and a fixed bottom input bar.

**Step 2: Implement Message**
Create a component that renders user prompts and "AI" responses (image results/loading states).

**Step 3: Implement InputBar**
Create a centered input bar with file upload support for Product, Reference, and Logo images.

---

### Task 3: API Integration & Polling

**Files:**
- Create: `apps/openai-image-gen/src/services/api.ts`
- Create: `apps/openai-image-gen/src/hooks/useChat.ts`

**Step 1: Create API Service**
Implement `generateOpenAI` and `getJobStatus` functions.

**Step 2: Implement useChat Hook**
Manage the conversation state, handling the transition from "Sending" -> "Polling" -> "Success/Fail".

**Step 3: Connect UI to Hook**
Wire up `ChatWindow` and `InputBar` to the `useChat` hook.

---

### Task 4: Polish & Styling

**Files:**
- Modify: `apps/openai-image-gen/src/index.css`
- Modify: `apps/openai-image-gen/src/App.tsx`

**Step 1: Refine Styling**
Apply a dark-mode-first, sleek "AI" aesthetic using Tailwind.

**Step 2: Add Loading States**
Ensure the "Assistant" bubbles show progress/skeleton states during generation.

---

### Task 5: Verification

**Step 1: Local Run**
Run: `npm run dev` in the app folder and verify it connects to the backend.

**Step 2: End-to-End Test**
Submit a prompt with an image and wait for the OpenAI result to appear in the chat.
