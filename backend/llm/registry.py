DEFAULT_REGISTRY: dict[str, str] = {
    "brand_extraction":        "gemini",
    "copy_generation":         "gemini",
    "meta_copy_generation":    "gemini",
    "image_prompt_generation": "gemini",
    "image_generation":        "gemini",
    "image_edit":              "gemini",
}

# Full registry per named provider — keys must match models registered in dependencies.py
PROVIDER_REGISTRIES: dict[str, dict[str, str]] = {
    "gemini": {
        "brand_extraction":        "gemini",
        "copy_generation":         "gemini",
        "meta_copy_generation":    "gemini",
        "image_prompt_generation": "gemini",
        "image_generation":        "gemini",
        "image_edit":              "gemini",
    },
    "openai": {
        "brand_extraction":        "openai",
        "copy_generation":         "openai",
        "meta_copy_generation":    "openai",
        "image_prompt_generation": "openai",
        "image_generation":        "openai",
        "image_edit":              "openai",
    },
}
