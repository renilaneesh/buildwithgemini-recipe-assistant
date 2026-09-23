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

"""Firestore backend tools for Recipe Assistant."""

import inspect
import os
import uuid
from datetime import datetime, timezone
import requests
from google import genai
from google.adk.tools import ToolContext
from google.cloud import firestore, storage

# Hardcode project ID to prevent Agent Platform project number issue
PROJECT_ID = "qwiklabs-gcp-01-1a15618a3a67"
BUCKET_NAME = "recipe-assistant-photos-1a15618a"

_db = None


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with hardcoded GCP project ID."""
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT_ID)
    return _db


def save_recipe(
    title: str,
    ingredients: list[str],
    instructions: str,
    prep_time_minutes: int = 20,
    cuisine: str = "General",
    tags: list[str] | None = None,
) -> str:
    """Saves a new recipe to the Firestore database.

    Args:
        title: The name/title of the recipe.
        ingredients: List of required ingredients.
        instructions: Step-by-step cooking instructions.
        prep_time_minutes: Preparation and cooking time in minutes.
        cuisine: Cuisine style (e.g., Italian, Mediterranean, American).
        tags: Optional list of tags (e.g., ["gluten-free", "dinner", "quick"]).

    Returns:
        Confirmation message with the created recipe ID.
    """
    db = get_firestore_client()
    doc_id = title.lower().replace(" ", "-").replace("/", "-")
    doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-") or str(uuid.uuid4())[:8]

    recipe_data = {
        "id": doc_id,
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "prep_time_minutes": prep_time_minutes,
        "cuisine": cuisine,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    db.collection("recipes").document(doc_id).set(recipe_data)
    return f"Successfully saved recipe '{title}' (ID: {doc_id}) to Firestore database."


def search_recipes(
    tag: str | None = None,
    ingredient: str | None = None,
    cuisine: str | None = None,
) -> str:
    """Searches and lists saved recipes in Firestore matching tag, ingredient, or cuisine filters.

    Args:
        tag: Optional tag to filter by (e.g. 'gluten-free', 'quick', 'vegetarian').
        ingredient: Optional ingredient keyword to filter by (e.g. 'chicken', 'quinoa', 'pasta').
        cuisine: Optional cuisine type to filter by (e.g. 'Italian', 'Mediterranean').

    Returns:
        Formatted summary of matching recipes found in Firestore.
    """
    db = get_firestore_client()
    recipes_ref = db.collection("recipes")

    docs = recipes_ref.stream()
    matched_recipes = []

    for doc in docs:
        data = doc.to_dict()
        if not data:
            continue

        # Filter by tag
        if tag and tag.lower() not in [t.lower() for t in data.get("tags", [])]:
            continue

        # Filter by ingredient
        if ingredient:
            ing_lower = ingredient.lower()
            if not any(ing_lower in ing.lower() for ing in data.get("ingredients", [])):
                continue

        # Filter by cuisine
        if cuisine and cuisine.lower() != data.get("cuisine", "").lower():
            continue

        matched_recipes.append(data)

    if not matched_recipes:
        return "No recipes found matching your search criteria."

    result_lines = [f"Found {len(matched_recipes)} recipe(s) in Firestore:\n"]
    for r in matched_recipes:
        result_lines.append(
            f"📖 **{r.get('title')}** ({r.get('cuisine', 'General')}, {r.get('prep_time_minutes', '?')} mins)"
        )
        result_lines.append(f"  - Tags: {', '.join(r.get('tags', []))}")
        result_lines.append(f"  - Ingredients: {', '.join(r.get('ingredients', []))}")
        result_lines.append(f"  - Instructions: {r.get('instructions')}\n")

    return "\n".join(result_lines)


def get_recipe_details(title: str) -> str:
    """Retrieves full details for a specific recipe from Firestore by title.

    Args:
        title: Name or partial title of the recipe to retrieve.

    Returns:
        Detailed recipe information or a not found message.
    """
    db = get_firestore_client()
    recipes_ref = db.collection("recipes")

    docs = recipes_ref.stream()
    title_lower = title.lower()

    for doc in docs:
        data = doc.to_dict()
        if data and title_lower in data.get("title", "").lower():
            return (
                f"📖 **{data.get('title')}**\n"
                f"Cuisine: {data.get('cuisine')}\n"
                f"Prep Time: {data.get('prep_time_minutes')} minutes\n"
                f"Tags: {', '.join(data.get('tags', []))}\n\n"
                f"**Ingredients:**\n"
                + "\n".join(f"- {i}" for i in data.get("ingredients", []))
                + "\n\n"
                f"**Instructions:**\n{data.get('instructions')}"
            )

    return f"Recipe '{title}' not found in Firestore."


async def generate_dish_photo(
    recipe_name: str,
    description: str | None = None,
    tool_context: ToolContext | None = None,
) -> str:
    """Generates an image of a recipe dish using gemini-3.1-flash-lite-image model,
    saves it to Playground artifacts, uploads it to Cloud Storage, and returns its public URL.

    Args:
        recipe_name: The name of the dish or recipe to generate an image for.
        description: Optional visual description (e.g. 'plated on a dark wooden table with fresh basil').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        The public HTTPS URL of the uploaded image in Cloud Storage.
    """
    genai_client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location="global",
    )

    prompt = f"A realistic, appetizing culinary photograph of {recipe_name}."
    if description:
        prompt += f" {description}"

    response = genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
    )

    part = response.candidates[0].content.parts[0]
    image_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/jpeg"

    doc_id = recipe_name.lower().replace(" ", "-").replace("/", "-")
    doc_id = "".join(c for c in doc_id if c.isalnum() or c == "-") or str(uuid.uuid4())[:8]
    ext = "png" if "png" in mime_type else "jpg"
    filename = f"{doc_id}.{ext}"

    # 1. Save artifact to ADK ToolContext (shows up in Playground Artifacts panel)
    if tool_context:
        res = tool_context.save_artifact(filename=filename, artifact=part)
        if inspect.isawaitable(res):
            await res

    # 2. Upload image bytes directly to public GCS bucket (no local file path returned)
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return public_url


def search_online_recipes(keyword: str) -> str:
    """Searches external live recipe database (TheMealDB) for real meal ideas by keyword or main ingredient.

    Args:
        keyword: Search query (e.g. 'chicken', 'pasta', 'salad', 'curry').

    Returns:
        Formatted summary of real online recipes with ingredients, category, and instructions.
    """
    api_key = os.getenv("THEMEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php"

    try:
        response = requests.get(url, params={"s": keyword}, timeout=10)
        response.raise_for_status()
        data = response.json()
        meals = data.get("meals")
        if not meals:
            return f"No online recipes found matching '{keyword}'."

        results = [f"Found {len(meals[:3])} online recipe(s) for '{keyword}':\n"]
        for meal in meals[:3]:
            title = meal.get("strMeal")
            category = meal.get("strCategory", "General")
            area = meal.get("strArea", "International")
            instructions = meal.get("strInstructions", "").strip()
            if len(instructions) > 250:
                instructions = instructions[:250] + "..."

            ingredients = []
            for i in range(1, 21):
                ing = meal.get(f"strIngredient{i}")
                meas = meal.get(f"strMeasure{i}")
                if ing and ing.strip():
                    ing_str = f"{meas.strip()} {ing.strip()}" if meas and meas.strip() else ing.strip()
                    ingredients.append(ing_str)

            results.append(
                f"🍲 **{title}** ({area} {category})\n"
                f"  - Ingredients: {', '.join(ingredients[:8])}\n"
                f"  - Instructions: {instructions}\n"
            )
        return "\n".join(results)
    except Exception as e:
        return f"Error fetching online recipes: {str(e)}"


