"""Seed the database with sample data."""
import requests

BASE = "http://localhost:8002/api"

# Login
r = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "admin123"})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

# Seed subjects
r = requests.post(f"{BASE}/admin/seed-subjects", headers=h)
print("Seed:", r.json())

# Get subjects
r = requests.get(f"{BASE}/questions/subjects")
subjects = r.json()
print("Subjects:", [(s["id"], s["name"]) for s in subjects])

passage = (
    "The migration patterns of monarch butterflies have long fascinated scientists. "
    "Each fall, millions of monarchs travel up to 3,000 miles from Canada and the "
    "United States to central Mexico. This remarkable journey is made even more "
    "extraordinary by the fact that no single butterfly completes the entire round "
    "trip. Instead, it takes multiple generations to complete the full migration cycle."
)

sample_questions = [
    # English (subject_id=1)
    {"subject_id": 1, "question_text": "Which of the following alternatives to the underlined portion would NOT be acceptable?",
     "option_a": "Furthermore,", "option_b": "In addition,", "option_c": "Meanwhile,", "option_d": "Moreover,",
     "correct_answer": "C", "difficulty": 2, "source_test": "Sample ACT 1"},
    {"subject_id": 1, "question_text": "The writer wants to add a sentence that effectively supports the main idea. Which choice best accomplishes this goal?",
     "option_a": "The research was conducted over several years.", "option_b": "The findings were published in a peer-reviewed journal.",
     "option_c": "The study confirmed that regular exercise improves cognitive function in all age groups.", "option_d": "Many scientists were involved in the study.",
     "correct_answer": "C", "difficulty": 3, "source_test": "Sample ACT 1"},
    {"subject_id": 1, "question_text": "Which choice most effectively combines the two sentences?",
     "option_a": "The novel was published in 1925, and it quickly became a bestseller.",
     "option_b": "Published in 1925, the novel quickly became a bestseller.",
     "option_c": "The novel was published in 1925; it quickly became a bestseller.",
     "option_d": "In 1925 the novel was published and quickly became a bestseller.",
     "correct_answer": "B", "difficulty": 2, "source_test": "Sample ACT 1"},

    # Math (subject_id=2)
    {"subject_id": 2, "question_text": "If 3x + 7 = 22, what is the value of x?",
     "option_a": "3", "option_b": "5", "option_c": "7", "option_d": "15",
     "correct_answer": "B", "difficulty": 1, "source_test": "Sample ACT 1"},
    {"subject_id": 2, "question_text": "What is the slope of the line passing through the points (2, 3) and (6, 11)?",
     "option_a": "1", "option_b": "2", "option_c": "3", "option_d": "4",
     "correct_answer": "B", "difficulty": 2, "source_test": "Sample ACT 1"},
    {"subject_id": 2, "question_text": "A circle has a radius of 5 cm. What is the area of the circle, in square centimeters?",
     "option_a": "10pi", "option_b": "15pi", "option_c": "20pi", "option_d": "25pi",
     "correct_answer": "D", "difficulty": 2, "source_test": "Sample ACT 1"},
    {"subject_id": 2, "question_text": "If f(x) = 2x^2 - 3x + 1, what is f(3)?",
     "option_a": "8", "option_b": "10", "option_c": "12", "option_d": "14",
     "correct_answer": "B", "difficulty": 3, "source_test": "Sample ACT 1"},

    # Reading (subject_id=3)
    {"subject_id": 3, "question_text": "Based on the passage, the author's main purpose is to:",
     "option_a": "argue against a commonly held belief", "option_b": "describe a personal experience",
     "option_c": "explain a scientific phenomenon", "option_d": "compare two historical events",
     "correct_answer": "C", "difficulty": 3, "source_test": "Sample ACT 1", "passage_text": passage},
    {"subject_id": 3, "question_text": "According to the passage, what makes the monarch butterfly migration extraordinary?",
     "option_a": "The distance traveled", "option_b": "The number of butterflies involved",
     "option_c": "The multi-generational nature of the journey", "option_d": "The speed at which they travel",
     "correct_answer": "C", "difficulty": 2, "source_test": "Sample ACT 1", "passage_text": passage},
    {"subject_id": 3, "question_text": "The word 'remarkable' as used in the passage most nearly means:",
     "option_a": "common", "option_b": "noteworthy", "option_c": "confusing", "option_d": "dangerous",
     "correct_answer": "B", "difficulty": 1, "source_test": "Sample ACT 1", "passage_text": passage},

    # Science (subject_id=4)
    {"subject_id": 4, "question_text": "Based on the data in Table 1, as temperature increases from 20C to 40C, the rate of enzyme activity:",
     "option_a": "increases only", "option_b": "decreases only", "option_c": "increases then decreases", "option_d": "remains constant",
     "correct_answer": "C", "difficulty": 3, "source_test": "Sample ACT 1"},
    {"subject_id": 4, "question_text": "Which of the following hypotheses is best supported by the results of Experiment 2?",
     "option_a": "pH has no effect on reaction rate", "option_b": "Higher pH always increases reaction rate",
     "option_c": "Optimal enzyme activity occurs at a specific pH", "option_d": "Temperature is more important than pH",
     "correct_answer": "C", "difficulty": 3, "source_test": "Sample ACT 1"},
    {"subject_id": 4, "question_text": "A student claims that doubling the concentration of substrate will double the reaction rate. Do the data support this claim?",
     "option_a": "Yes, because the data show a linear relationship", "option_b": "Yes, because more substrate means more collisions",
     "option_c": "No, because the rate plateaus at high concentrations", "option_d": "No, because temperature was not controlled",
     "correct_answer": "C", "difficulty": 4, "source_test": "Sample ACT 1"},
]

r = requests.post(f"{BASE}/questions/bulk", json=sample_questions, headers=h)
print(f"Created {len(r.json())} questions")

# Create a sample test
test_data = {
    "name": "ACT Practice Test 1",
    "description": "A sample practice test covering all four ACT sections with timed sections.",
    "time_limit_minutes": 30,
    "sections": [
        {"subject_id": 1, "name": "English", "num_questions": 3, "time_limit_minutes": 8, "order": 1, "auto_pick": True},
        {"subject_id": 2, "name": "Math", "num_questions": 4, "time_limit_minutes": 10, "order": 2, "auto_pick": True},
        {"subject_id": 3, "name": "Reading", "num_questions": 3, "time_limit_minutes": 7, "order": 3, "auto_pick": True},
        {"subject_id": 4, "name": "Science", "num_questions": 3, "time_limit_minutes": 5, "order": 4, "auto_pick": True},
    ],
}
r = requests.post(f"{BASE}/tests/", json=test_data, headers=h)
print("Test created:", r.json().get("name"), "- ID:", r.json().get("id"))

# Dashboard
r = requests.get(f"{BASE}/admin/dashboard", headers=h)
stats = r.json()
print(f"\nDashboard: {stats['total_questions']} questions, {stats['total_tests']} tests, {stats['total_users']} users")
print("By subject:", stats["questions_by_subject"])
