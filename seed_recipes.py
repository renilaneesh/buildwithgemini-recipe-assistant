"""Firestore Seeding Script for Recipe Assistant Agent.

Inserts 3 rich, high-quality sample recipes into the 'recipes' collection in Firestore.
"""

from app.tools import get_firestore_client, save_recipe


def main():
    print("Initializing Firestore client and seeding recipes...")

    # 1. Creamy Garlic Parmesan Pasta (Exact required name & favorite tag)
    r1 = save_recipe(
        title="Creamy Garlic Parmesan Pasta",
        ingredients=[
            "8 oz fettuccine or penne pasta",
            "2 tbsp unsalted butter",
            "4 cloves garlic, minced",
            "1 cup heavy cream",
            "1 cup freshly grated Parmesan cheese",
            "1/2 tsp salt & black pepper",
            "Fresh parsley for garnish",
        ],
        instructions="1. Boil pasta in salted water until al dente.\n2. Melt butter in a skillet over medium heat and sauté garlic for 1 minute.\n3. Pour in heavy cream and bring to a gentle simmer.\n4. Stir in grated Parmesan until creamy and smooth.\n5. Toss pasta in sauce, garnish with fresh parsley and black pepper, and serve warm.",
        prep_time_minutes=20,
        cuisine="Italian",
        tags=["favorite", "pasta", "quick", "dinner", "vegetarian"],
    )
    print(" ->", r1)

    # 2. Tuscan Lemon Herb Chicken
    r2 = save_recipe(
        title="Tuscan Lemon Herb Chicken",
        ingredients=[
            "4 boneless chicken breasts",
            "2 tbsp olive oil",
            "3 cloves garlic, minced",
            "1/4 cup fresh lemon juice",
            "1 tsp dried oregano & rosemary",
            "Fresh basil leaves",
            "Salt and black pepper",
        ],
        instructions="1. Season chicken breasts with salt, pepper, and herbs.\n2. Heat olive oil in a skillet over medium-high heat.\n3. Sear chicken for 6-7 minutes per side until golden brown.\n4. Add minced garlic and lemon juice, simmer for 2 minutes.\n5. Garnish with fresh basil leaves.",
        prep_time_minutes=25,
        cuisine="Mediterranean",
        tags=["favorite", "chicken", "gluten-free", "dinner"],
    )
    print(" ->", r2)

    # 3. Avocado Citrus Quinoa Bowl
    r3 = save_recipe(
        title="Avocado Citrus Quinoa Bowl",
        ingredients=[
            "1 cup cooked white quinoa",
            "1 ripe avocado, sliced",
            "1 fresh orange, segmented",
            "1/2 cup cherry tomatoes, halved",
            "2 cups fresh baby spinach",
            "2 tbsp lemon herb vinaigrette",
        ],
        instructions="1. Base bowl with fresh baby spinach and warm cooked quinoa.\n2. Arrange sliced avocado, orange segments, and halved cherry tomatoes on top.\n3. Drizzle with lemon vinaigrette and toss gently.",
        prep_time_minutes=15,
        cuisine="Healthy Fusion",
        tags=["healthy", "gluten-free", "vegan", "lunch"],
    )
    print(" ->", r3)

    print(
        "✅ Firestore seeding complete! 3 sample recipes successfully written to Firestore 'recipes' collection."
    )


if __name__ == "__main__":
    main()
