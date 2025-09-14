"""Greet someone with a personalized message. If no name is provided, defaults to "world"."""

def greet(name: str = 'world') -> str:
    return f'hello {name}'