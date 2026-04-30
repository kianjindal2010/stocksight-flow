from __future__ import annotations

from typing import Any


def quiz_default_doc() -> dict[str, Any]:
    return {
        "streak": 0,
        "completed": 0,
        "history": [],
        "completed_quiz_module_ids": [],
        "module_scores": {},
        "milestones": [
            "Pass first module quiz",
            "Pass 5 module quizzes",
            "Pass all 20 module quizzes",
        ],
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _curriculum_rows(curriculum: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, module in enumerate(curriculum, start=1):
        module_id = _text(module.get("id"))
        if not module_id:
            continue
        topics = module.get("topics") if isinstance(module.get("topics"), list) else []
        clean_topics = [_text(topic) for topic in topics if _text(topic)]
        rows.append(
            {
                "id": module_id,
                "index": index,
                "title": _text(module.get("title")) or f"Module {index}",
                "summary": _text(module.get("summary")) or "Build a clearer investing process.",
                "practice": _text(module.get("practice")) or "Apply the concept to one paper-trading decision.",
                "topics": clean_topics[:4] or ["core idea", "risk check", "decision process", "review habit"],
            }
        )
    return rows


def valid_module_ids(curriculum: list[dict[str, Any]]) -> list[str]:
    return [row["id"] for row in _curriculum_rows(curriculum)]


def select_module_id(
    curriculum: list[dict[str, Any]],
    requested_module_id: str | None = None,
    completed_module_ids: list[str] | None = None,
) -> str:
    rows = _curriculum_rows(curriculum)
    module_ids = [row["id"] for row in rows]
    requested = _text(requested_module_id)
    if requested in module_ids:
        return requested

    completed = {_text(module_id) for module_id in (completed_module_ids or [])}
    for module_id in module_ids:
        if module_id not in completed:
            return module_id
    return module_ids[0] if module_ids else ""


def quiz_catalog(
    curriculum: list[dict[str, Any]],
    quiz_state: dict[str, Any] | None = None,
    completed_module_ids: list[str] | None = None,
    selected_module_id: str | None = None,
) -> list[dict[str, Any]]:
    state = quiz_state if isinstance(quiz_state, dict) else {}
    scores = state.get("module_scores") if isinstance(state.get("module_scores"), dict) else {}
    completed_quizzes = state.get("completed_quiz_module_ids")
    if not isinstance(completed_quizzes, list):
        completed_quizzes = []
    completed_quiz_set = {_text(module_id) for module_id in completed_quizzes}
    completed_module_set = {_text(module_id) for module_id in (completed_module_ids or [])}
    rows = []
    for module in _curriculum_rows(curriculum):
        module_id = module["id"]
        score_doc = scores.get(module_id) if isinstance(scores.get(module_id), dict) else {}
        rows.append(
            {
                "id": module_id,
                "index": module["index"],
                "title": module["title"],
                "question_count": 20,
                "is_selected": module_id == selected_module_id,
                "is_quiz_passed": module_id in completed_quiz_set,
                "is_module_completed": module_id in completed_module_set,
                "best_score_pct": int(score_doc.get("best_score_pct") or 0),
                "attempts": int(score_doc.get("attempts") or 0),
            }
        )
    return rows


def _unique_options(correct: str, distractors: list[str], answer_slot: int) -> tuple[list[str], int]:
    options: list[str] = []
    seen: set[str] = set()
    for raw in [correct, *distractors, "Write a clear note before acting", "Review the result after the decision"]:
        value = _text(raw)
        key = value.lower()
        if value and key not in seen:
            options.append(value)
            seen.add(key)
        if len(options) == 4:
            break
    correct_text = options[0]
    answer_index = max(0, min(3, answer_slot % 4))
    if answer_index != 0:
        options[0], options[answer_index] = options[answer_index], options[0]
    return options, options.index(correct_text)


def _question(
    *,
    module: dict[str, Any],
    number: int,
    prompt: str,
    correct: str,
    distractors: list[str],
    explanation: str,
) -> dict[str, Any]:
    choices, answer_index = _unique_options(correct, distractors, number)
    return {
        "id": f"{module['id']}_q{number:02d}",
        "module_id": module["id"],
        "module": module["title"],
        "prompt": prompt,
        "choices": choices,
        "answer_index": answer_index,
        "explanation": explanation,
    }


def _other_values(rows: list[dict[str, Any]], current_id: str, key: str) -> list[str]:
    values: list[str] = []
    for row in rows:
        if row["id"] == current_id:
            continue
        value = row.get(key)
        if isinstance(value, list):
            values.extend(_text(item) for item in value if _text(item))
        else:
            text = _text(value)
            if text:
                values.append(text)
    return values


def _topic(module: dict[str, Any], index: int) -> str:
    topics = module.get("topics") if isinstance(module.get("topics"), list) else []
    if not topics:
        return "core idea"
    return _text(topics[index % len(topics)]) or "core idea"


def quiz_question_bank(curriculum: list[dict[str, Any]], module_id: str | None = None) -> list[dict[str, Any]]:
    rows = _curriculum_rows(curriculum)
    if not rows:
        return []

    selected_id = select_module_id(curriculum, module_id)
    selected_rows = [row for row in rows if row["id"] == selected_id] if module_id else rows
    questions: list[dict[str, Any]] = []

    for module in selected_rows:
        module_id = module["id"]
        title = module["title"]
        topics = module["topics"]
        other_summaries = _other_values(rows, module_id, "summary")
        other_practices = _other_values(rows, module_id, "practice")
        other_topics = _other_values(rows, module_id, "topics")
        topic_pair = f"{_topic(module, 0)} and {_topic(module, 1)}"

        questions.extend(
            [
                _question(
                    module=module,
                    number=1,
                    prompt=f"What is the main goal of {title}?",
                    correct=module["summary"],
                    distractors=[
                        "Memorize ticker symbols without linking them to decisions.",
                        "Trade faster by skipping risk checks.",
                        *(other_summaries[:2]),
                    ],
                    explanation=f"{title} is about {module['summary'].rstrip('.')}.",
                ),
                _question(
                    module=module,
                    number=2,
                    prompt=f"Which practice task best matches {title}?",
                    correct=module["practice"],
                    distractors=[
                        "Place a random paper trade without a written reason.",
                        "Only check whether the market closed higher or lower.",
                        *(other_practices[:2]),
                    ],
                    explanation="The practice task converts the module into a concrete learning action.",
                ),
            ]
        )

        for index in range(4):
            offset = index + 3
            topic = _topic(module, index)
            questions.append(
                _question(
                    module=module,
                    number=offset,
                    prompt=f"Which topic belongs in the {title} module?",
                    correct=topic,
                    distractors=[
                        "guessing intraday reversals",
                        "doubling down after a loss",
                        *other_topics[offset : offset + 2],
                    ],
                    explanation=f"{topic} is one of the study points for {title}.",
                )
            )

        templates = [
            (
                f"Before applying {_topic(module, 0)}, what should you write down?",
                "How it changes your entry, exit, or risk decision.",
                ["The first headline you saw.", "A larger trade size for excitement.", "Nothing, because notes slow you down."],
                "A written link between concept and decision makes the lesson reviewable.",
            ),
            (
                f"Which response shows discipline while using {_topic(module, 1)}?",
                "Compare it with your plan before increasing risk.",
                ["Ignore the plan if the chart feels strong.", "Use it only after a loss.", "Treat it as a guarantee."],
                "Disciplined learners test the idea against the plan before adding risk.",
            ),
            (
                f"What is the best sign you understand {_topic(module, 2)}?",
                "You can explain it simply and apply it to one current holding.",
                ["You can repeat the term from memory.", "You never need to review it again.", "You use it to justify every trade."],
                "Understanding shows up when you can explain and apply the topic clearly.",
            ),
            (
                f"Which mistake should {title} help you avoid?",
                "Making trades that cannot be reviewed later.",
                ["Writing a trade thesis.", "Keeping position sizes controlled.", "Comparing outcomes with your plan."],
                "The module should make your decisions more deliberate and easier to review.",
            ),
            (
                f"How should the {title} practice task be completed?",
                "With one concrete example and a short written takeaway.",
                ["By clicking through it without notes.", "By copying someone else's trade.", "By waiting until every concept feels perfect."],
                "One concrete example is enough to turn the concept into usable progress.",
            ),
            (
                f"If {title} conflicts with excitement about a trade, what should win?",
                "The written plan and risk limits.",
                ["The feeling that the trade will work.", "The biggest position size available.", "A social media opinion."],
                "Learning progress depends on following the process when emotions get loud.",
            ),
            (
                "What should you do after a quiz question exposes a gap?",
                "Review the related topic and retake the module quiz.",
                ["Ignore the explanation.", "Mark the module complete anyway.", "Increase risk to learn faster."],
                "A missed question is a useful signal for what to study next.",
            ),
            (
                "Which record best supports learning progress?",
                "A dated note of the module, quiz score, and action taken.",
                ["Only the final account value.", "A list of winning ticker symbols.", "A screenshot with no explanation."],
                "Progress is easier to sustain when learning actions are recorded.",
            ),
            (
                "What does passing this module quiz unlock in the app?",
                "Credit toward module learning progress.",
                ["Guaranteed investment returns.", "Permission to ignore risk controls.", "A live trade recommendation."],
                "Passing a module quiz marks that module as completed in learning progress.",
            ),
            (
                f"Which answer best reflects the {title} summary?",
                module["summary"],
                ["Trade without reviewing risk.", "Focus only on short-term price noise.", *(other_summaries[2:4])],
                "The module summary is the clearest statement of what this lesson is for.",
            ),
            (
                f"Which topic pair belongs together in {title}?",
                topic_pair,
                [
                    "revenge trading and oversized bets",
                    "random entries and skipped reviews",
                    f"{other_topics[0] if other_topics else 'cash flow'} and {other_topics[1] if len(other_topics) > 1 else 'market timing'}",
                ],
                "The pair is built from topics listed in this module.",
            ),
            (
                f"When should you revisit {title}?",
                "When your trades show repeated mistakes in its topics.",
                ["Only after every position is profitable.", "Never after passing once.", "Only when the market is closed for a holiday."],
                "Revisiting a module is useful when real activity exposes the same weakness again.",
            ),
            (
                f"How does {title} improve decision quality?",
                "It turns vague reactions into checked, repeatable choices.",
                ["It removes all uncertainty.", "It predicts the exact next price.", "It replaces the need for a trading plan."],
                "Good learning modules improve the process, not certainty.",
            ),
            (
                f"What is the safest next action after finishing {title}?",
                "Apply the practice task before taking larger risk.",
                ["Skip the practice and move to live trades.", "Increase leverage immediately.", "Forget the topic once the quiz is passed."],
                "The practice task is the bridge from knowledge to safer behavior.",
            ),
        ]
        for number, (prompt, correct, distractors, explanation) in enumerate(templates, start=7):
            questions.append(
                _question(
                    module=module,
                    number=number,
                    prompt=prompt,
                    correct=correct,
                    distractors=distractors,
                    explanation=explanation,
                )
            )

    return questions


def quiz_report(questions: list[dict[str, Any]], selected_answers: dict[str, str]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    correct = 0
    unanswered = 0
    for question in questions:
        question_id = _text(question.get("id"))
        choices = question.get("choices") if isinstance(question.get("choices"), list) else []
        selected_raw = _text(selected_answers.get(question_id, ""))
        try:
            selected_idx = int(selected_raw)
        except ValueError:
            selected_idx = -1
        in_range = 0 <= selected_idx < len(choices)
        selected_text = _text(choices[selected_idx]) if in_range else ""
        try:
            answer_idx = int(question.get("answer_index"))
        except (TypeError, ValueError):
            answer_idx = -1
        answer_in_range = 0 <= answer_idx < len(choices)
        correct_text = _text(choices[answer_idx]) if answer_in_range else ""
        is_correct = in_range and answer_in_range and selected_idx == answer_idx
        if not in_range:
            unanswered += 1
        if is_correct:
            correct += 1
        details.append(
            {
                "id": question_id,
                "prompt": _text(question.get("prompt")),
                "selected_text": selected_text,
                "correct_text": correct_text,
                "is_correct": is_correct,
                "explanation": _text(question.get("explanation")),
            }
        )
    total = len(questions)
    safe_total = max(1, total)
    score_pct = int(round((correct / safe_total) * 100))
    return {
        "total": total,
        "correct": correct,
        "incorrect": max(0, total - correct),
        "unanswered": unanswered,
        "score_pct": score_pct,
        "passed": score_pct >= 70,
        "details": details,
    }
