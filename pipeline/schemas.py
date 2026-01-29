from typing import Literal

from pydantic import BaseModel, Field


class StudyTableRow(BaseModel):
    """A single row in the study table representing a medical condition."""

    Condition: str
    Risk_Factors: str = Field(alias="Risk Factors")
    Etiology: str
    Pathology: str
    Pathophysiology: str
    Clinical_Presentation: str = Field(alias="Clinical Presentation")
    Diagnosis_Key_Findings: str = Field(alias="Diagnosis / Key Findings")
    Histology_Key_Findings: str = Field(alias="Histology Key Findings")
    Prognosis: str
    Treatment: str
    Classic_Step_1_Style_Question_Stem: str = Field(
        alias="Classic Step 1–Style Question Stem"
    )
    Photos_from_Lecture: str = Field(alias="Photos from Lecture")
    Additional_Notes_Important_Things: str = Field(
        alias="Additional Notes/Important Things"
    )
    Mnemonic: str

    model_config = {"populate_by_name": True}


class StudyTable(BaseModel):
    """Study table containing rows of medical conditions."""

    rows: list[StudyTableRow] = Field(
        description="Array of CSV rows. Each item maps 1:1 to a CSV row with the specified headers."
    )


class QuestionChoices(BaseModel):
    """Multiple choice options for a vignette question."""

    A: str
    B: str
    C: str
    D: str
    E: str


class VignetteQuestion(BaseModel):
    """A single vignette question for a learning objective."""

    question_number: int
    difficulty: Literal["Easy", "Medium", "Hard"]
    vignette: str = Field(description="The clinical scenario/stem")
    question: str = Field(description="The actual question being asked")
    choices: QuestionChoices
    correct_answer: Literal["A", "B", "C", "D", "E"]
    explanation: str = Field(
        description="Explanation of why the correct answer is right and why distractors are wrong"
    )


class LearningObjective(BaseModel):
    """A learning objective with associated vignette questions."""

    objective: str = Field(description="The learning objective from the lecture")
    questions: list[VignetteQuestion] = Field(
        description="2-3 vignette questions for this learning objective"
    )


class VignetteQuestions(BaseModel):
    """Vignette questions organized by learning objectives."""

    learning_objectives: list[LearningObjective] = Field(
        description="Array of learning objectives with their associated vignette questions"
    )
