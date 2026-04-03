---
name: Autonomous task queue progression
description: Wang should auto-progress through task queue without asking user for confirmation on each step
type: feedback
---

按 queue 顺序自动推进任务分配，不逐个向用户确认。除非遇到决定不了的问题才问用户。

**Why:** 用户明确说"不用问我，循序渐进一直分配到所有任务完成才是正确的。除非有决定不了的，再来问我"
**How to apply:** 每次 Yu 完成一个任务，立刻分配 queue 中的下一个，不等用户确认。
