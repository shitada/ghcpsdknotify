以下のクイズの採点を行ってください。
ソース資料と問題文に基づいて、ユーザーの回答を評価してください。

## ソース資料
{source_content}

## Q1（4択）
### 問題
{q1_question_text}
### ユーザーの選択
{q1_user_choice}

## Q2（記述）
### 問題
{q2_question_text}
### ユーザーの回答
{q2_user_answer}

## 採点基準
- Q1: 正解/不正解を判定し、正解の選択肢と解説を付けてください。
- Q2:
  - good: 核心的なポイントを正しく説明できている
  - partial: 方向性は合っているが重要な要素が欠けている
  - poor: 根本的に誤っている、または回答になっていない

## 出力形式（JSON のみ出力）
{{
  "q1_correct": true,
  "q1_correct_answer": "B",
  "q1_explanation": "解説文…",
  "q2_evaluation": "good|partial|poor",
  "q2_feedback": "フィードバックコメント"
}}
