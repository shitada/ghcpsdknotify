# Demo Video Scenario (3 Minutes)

**Target Length**: 3 minutes
**Format**: Screen recording with voiceover (or text captions)
**Goal**: Demonstrate the core value proposition (turning local notes into active intelligence) and show both Feature A (Briefing) and Feature B (Quiz) in action.

---

## 0:00 - 0:30 | Introduction & Setup (30s)
- **Visual**: Show a folder full of local Markdown notes (e.g., `C:\MyNotes`). Open one note briefly to show it contains standard text (e.g., notes on "React Server Components" or "Azure OpenAI").
- **Narration/Caption**: "We all have hundreds of local notes. But how often do we review them or update them with the latest news? *Personal AI Daily Briefing Agent* solves this."
- **Action**: Start the application. Show the system tray icon appearing. Right-click the tray icon and open "Settings" to show the UI where the user selects their notes folder and sets the schedule.

## 0:30 - 1:30 | Feature A: Daily Briefing (60s)
- **Action**: Right-click the tray icon and select "Run Feature A (Briefing) Now" to force a manual run.
- **Visual**: Show the Windows Toast Notification popping up: "Your Daily Briefing is ready!"
- **Action**: Click the notification. The HTML Viewer opens.
- **Narration/Caption**: "The agent randomly selects notes, reads the context, and uses the Copilot SDK with Bing Search (and WorkIQ MCP) to find the latest updates on those specific topics."
- **Visual**: Scroll through the generated briefing. Highlight how it connects a local note topic (e.g., "React") to a recent news article or documentation update, complete with source URLs.

## 1:30 - 2:30 | Feature B: Review Quiz & Spaced Repetition (60s)
- **Action**: Right-click the tray icon and select "Run Feature B (Quiz) Now".
- **Visual**: A new Toast Notification appears. Click it to open the Quiz Viewer.
- **Narration/Caption**: "To reinforce learning, Feature B generates a spaced-repetition quiz based purely on your local note content."
- **Action**: 
  - Show Q1 (Multiple Choice). Select an answer.
  - Show Q2 (Free-form text). Type a brief answer.
  - Click "Submit".
- **Visual**: Show the loading state, then the scoring result screen.
- **Narration/Caption**: "A separate LLM session scores the answers. Based on the result, the SM-2 algorithm adjusts the next review interval (e.g., from 1 day to 3 days)."

## 2:30 - 3:00 | Architecture & Conclusion (30s)
- **Visual**: Briefly show the Architecture Diagram (from the presentation deck) or the VS Code terminal showing the Copilot SDK logs.
- **Narration/Caption**: "Everything runs locally. Files are never uploaded—only text is sent via the GitHub Copilot SDK, ensuring enterprise-grade data protection."
- **Visual**: Show the GitHub repo link or a final title card.
- **Narration/Caption**: "Turn your static notes into a dynamic AI assistant. Thank you."

---

### Tips for Recording
- **Pre-populate data**: Have 5-10 realistic-looking Markdown files ready in a folder.
- **Speed up generation**: If the LLM generation takes 10-15 seconds, you can edit the video to speed up that specific waiting period to keep the video under 3 minutes.
- **Resolution**: Record in 1080p so the text in the HTML viewer is readable.