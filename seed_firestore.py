import os
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-02-e82d983c2fc0"

def seed():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)

    seeded_items = [
        {
            "id": "bench_press",
            "name": "Barbell Bench Press",
            "category": "Strength",
            "target_muscle": "Chest",
            "default_sets": 4,
            "default_reps": 8,
            "description": "Compound upper body pushing movement focusing on pecs, triceps, and anterior deltoids."
        },
        {
            "id": "barbell_squat",
            "name": "Barbell Back Squat",
            "category": "Strength",
            "target_muscle": "Legs",
            "default_sets": 4,
            "default_reps": 10,
            "description": "Primary lower body compound movement targeting quadriceps, glutes, and hamstrings."
        },
        {
            "id": "deadlift",
            "name": "Conventional Deadlift",
            "category": "Strength",
            "target_muscle": "Back",
            "default_sets": 3,
            "default_reps": 5,
            "description": "Full body posterior chain movement building back, glute, and hip strength."
        },
        {
            "id": "pullup",
            "name": "Bodyweight Pull-Up",
            "category": "Calisthenics",
            "target_muscle": "Back",
            "default_sets": 3,
            "default_reps": 12,
            "description": "Upper body vertical pulling exercise targeting lats, upper back, and biceps."
        },
        {
            "id": "hiit_sprints",
            "name": "Interval Treadmill Sprints",
            "category": "Cardio",
            "target_muscle": "Full Body",
            "default_sets": 8,
            "default_reps": 30,
            "description": "High-intensity cardio intervals for cardiovascular endurance and conditioning."
        }
    ]

    collection_ref = db.collection("exercises")
    for item in seeded_items:
        doc_ref = collection_ref.document(item["id"])
        doc_ref.set(item)
        print(f"Seeded exercise: {item['name']} ({item['id']})")

    print("Firestore seeding complete!")

if __name__ == "__main__":
    seed()
