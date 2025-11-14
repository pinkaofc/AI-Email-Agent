def review_email(email: dict, response: str) -> str:
    """
    Simulates human review of the AI-generated email response.
    Displays the response and allows the reviewer to modify it if needed.

    Args:
        email (dict): The email being processed (for context).
        response (str): The AI-generated response.

    Returns:
        str: The final response text after optional human review.
    """
    print("\n--- Generated Response ---\n")
    print(response)
    print("\n---------------------------")

    user_input = input("Do you want to make any changes to the response? (y/n): ").strip().lower()
    if user_input == "y":
        modified_response = input("\nEnter the corrected response:\n").strip()
        return modified_response
    return response
