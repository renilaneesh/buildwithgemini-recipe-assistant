# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Seed script for Recipe Assistant Firestore database."""

from datetime import datetime, timezone
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-1a15618a3a67"

SEEDED_RECIPES = [
    {
        "id": "gluten-free-carbonara",
        "title": "Gluten-Free Spaghetti Carbonara",
        "ingredients": [
            "gluten-free spaghetti",
            "eggs",
            "pancetta",
            "parmesan cheese",
            "black pepper",
        ],
        "instructions": (
            "1. Boil gluten-free pasta in salted water.\n"
            "2. Fry pancetta until crispy.\n"
            "3. Whisk eggs and grated parmesan in a bowl.\n"
            "4. Toss hot pasta with pancetta, remove from heat, and mix in egg mixture with black pepper."
        ),
        "prep_time_minutes": 20,
        "cuisine": "Italian",
        "tags": ["gluten-free", "pasta", "dinner", "quick"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "mediterranean-quinoa-salad",
        "title": "Mediterranean Quinoa Salad",
        "ingredients": [
            "quinoa",
            "cucumbers",
            "cherry tomatoes",
            "feta cheese",
            "olives",
            "olive oil",
            "lemon juice",
        ],
        "instructions": (
            "1. Cook quinoa and let cool.\n"
            "2. Dice cucumbers, tomatoes, and olives.\n"
            "3. Combine quinoa, vegetables, and crumbled feta.\n"
            "4. Dress with olive oil, lemon juice, salt, and pepper."
        ),
        "prep_time_minutes": 15,
        "cuisine": "Mediterranean",
        "tags": ["gluten-free", "vegetarian", "healthy", "lunch"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "lemon-herb-grilled-chicken",
        "title": "Lemon Herb Grilled Chicken",
        "ingredients": [
            "chicken breast",
            "lemon juice",
            "garlic",
            "rosemary",
            "olive oil",
            "salt",
        ],
        "instructions": (
            "1. Marinate chicken breasts in lemon juice, minced garlic, rosemary, and olive oil for 30 min.\n"
            "2. Preheat grill or skillet over medium-high heat.\n"
            "3. Grill chicken for 6-8 minutes per side until internal temperature reaches 165°F (74°C).\n"
            "4. Rest 5 minutes before serving."
        ),
        "prep_time_minutes": 40,
        "cuisine": "American",
        "tags": ["gluten-free", "high-protein", "dinner", "chicken"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
]


def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    recipes_ref = db.collection("recipes")

    print(f"Seeding Firestore collection 'recipes' in project '{PROJECT_ID}'...")
    for recipe in SEEDED_RECIPES:
        doc_id = recipe["id"]
        recipes_ref.document(doc_id).set(recipe)
        print(f"  - Seeded recipe: {recipe['title']} (ID: {doc_id})")

    print("Firestore seeding complete!")


if __name__ == "__main__":
    seed_database()
