# Project Summary (150 words)

**Personal AI Daily Briefing Agent** is a Windows desktop application that transforms a user's local Markdown notes into actionable intelligence and active learning opportunities. 

While LLMs are powerful, users struggle to effectively ingest their vast personal knowledge bases within limited context windows. Our agent solves this by using a weighted random selection and discovery rotation strategy to extract the most relevant local notes. 

It delivers two core features via the GitHub Copilot SDK:
1. **Daily Briefing**: Analyzes note topics and uses Bing Search and WorkIQ MCP to summarize the latest external news and internal updates.
2. **Review Quiz**: Auto-generates spaced-repetition quizzes (multiple-choice and free-form) from note content, scored by the LLM to reinforce learning.

Built with Python, it runs locally, ensuring privacy by never uploading files. It seamlessly integrates into daily workflows via Windows toast notifications, turning static notes into a dynamic, personalized AI assistant.