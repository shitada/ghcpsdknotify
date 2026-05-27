Please score the following quiz.
Evaluate the user's answers based on the source material and questions.

## Source Material
{source_content}

## Q1 (Multiple Choice)
### Question
{q1_question_text}
### User's Choice
{q1_user_choice}

## Q2 (Free-form)
### Question
{q2_question_text}
### User's Answer
{q2_user_answer}

## Scoring Criteria
- Q1: Determine correct/incorrect, and provide the correct choice with an explanation.
- Q2:
  - good: Correctly explains the core points
  - partial: On the right track but missing important elements
  - poor: Fundamentally wrong or not an answer

## Output Format (JSON only)
{{
  "q1_correct": true,
  "q1_correct_answer": "B",
  "q1_explanation": "Explanation text...",
  "q2_evaluation": "good|partial|poor",
  "q2_feedback": "Feedback comment"
}}
