from chatlas import content_pdf_file, ChatOpenAI, Chat
from chatlas.types import ChatResponseAsync


def get_chat() -> Chat:
    chat = ChatOpenAI(
        system_prompt="""
        You are a helpful AI tutor for medical students.
        Keep the overall tone encouraging and professional yet friendly.
        Make sure to focus on key details, but especially those noted as "Learning Objectives".
        Generate all responses in raw Markdown format. Do not wrap the Markdown in a code block.

        Example:
        # Handout for Lecture 1
        ## Learning Objectives
        - Understand the basic principles of pharmacology.
        - Describe the mechanisms of drug action.
        - Identify the major classes of drugs.
        
        ## Slide 1
        Content from slide 1.

        ## Slide 2
        Content from slide 2.
        """,
        model="gpt-4.1"
    )
    return chat


async def generate_handout(file: str) -> ChatResponseAsync:
    prompt = """Attached is a medical school slide deck. Review the content in the slides and generate a multiple page handout covering all information. 
Include references to images from the slides in the handout where applicable.
If the slides include Learning Objectives, place those first verbatim.
"""
    chat = get_chat()
    return await chat.stream_async(prompt, content_pdf_file(file))

async def generate_quiz(file: str) -> ChatResponseAsync:
    prompt = """Attached is a medical school slide deck. Review the content in the slides and generate a multiple page, multiple choice quiz covering all information.
Make sure to include correct answers to each question **at the end of the quiz**. Justify why each answer is right or wrong."""
    chat = get_chat()
    return await chat.stream_async(prompt, content_pdf_file(file))

async def generate_summary(file: str) -> ChatResponseAsync:
    prompt = """Attached is a medical school slide deck. Generate a brief summary of keypoints to know based on the content of the slides."""
    chat = get_chat()
    return await chat.stream_async(prompt, content_pdf_file(file))