"""Test script to preview the vignette PDF formatting with mock data."""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape
from xhtml2pdf import pisa

# Mock data for testing
mock_learning_objectives = [
    {
        "objective": "Understand the pathophysiology and clinical presentation of Primary Biliary Cholangitis (PBC)",
        "questions": [
            {
                "question_number": 1,
                "difficulty": "Medium",
                "vignette": "A 48-year-old woman presents to her physician with a 6-month history of progressive fatigue and generalized itching that is worse at night. She has no significant past medical history. Physical examination reveals mild scleral icterus and yellowish plaques around her eyelids bilaterally. Laboratory studies show: Alkaline phosphatase: 450 U/L (normal: 30-120 U/L), Total bilirubin: 2.1 mg/dL (normal: 0.1-1.2 mg/dL), AST: 52 U/L, ALT: 48 U/L. Anti-mitochondrial antibody testing is positive.",
                "question": "Which of the following best describes the underlying pathophysiology of this patient's condition?",
                "choices": {
                    "A": "Autoimmune destruction of hepatocytes leading to centrilobular necrosis",
                    "B": "Immune-mediated destruction of intrahepatic bile ducts causing cholestasis",
                    "C": "Viral infection causing acute hepatocellular injury",
                    "D": "Obstruction of the common bile duct by gallstones",
                    "E": "Drug-induced hepatotoxicity affecting zone 3 hepatocytes",
                },
                "correct_answer": "B",
                "explanation": "This patient has Primary Biliary Cholangitis (PBC), characterized by autoimmune destruction of small intrahepatic bile ducts. The positive anti-mitochondrial antibody (AMA) is virtually diagnostic. The destruction leads to cholestasis, causing the elevated ALP, pruritus (from bile salt deposition in skin), and xanthelasma (cholesterol deposits from impaired bile excretion). Option A describes autoimmune hepatitis. Option C would show different serologic markers. Option D would show dilated bile ducts on imaging. Option E would have a medication history.",
            },
            {
                "question_number": 2,
                "difficulty": "Easy",
                "vignette": "A 55-year-old woman with known Primary Biliary Cholangitis presents for follow-up. She has been on ursodeoxycholic acid for 2 years. Recent labs show improving alkaline phosphatase levels but she continues to have mild pruritus.",
                "question": "Which of the following laboratory findings is most specific for the diagnosis of Primary Biliary Cholangitis?",
                "choices": {
                    "A": "Elevated alkaline phosphatase",
                    "B": "Positive anti-mitochondrial antibody (AMA)",
                    "C": "Elevated IgM levels",
                    "D": "Positive anti-nuclear antibody (ANA)",
                    "E": "Elevated gamma-glutamyl transferase (GGT)",
                },
                "correct_answer": "B",
                "explanation": "Anti-mitochondrial antibody (AMA) is highly specific for PBC, present in over 95% of patients. While elevated ALP (A), IgM (C), and GGT (E) are commonly seen in PBC, they are not specific and can be elevated in many other liver conditions. ANA (D) can be positive in PBC but is more associated with autoimmune hepatitis.",
            },
            {
                "question_number": 3,
                "difficulty": "Hard",
                "vignette": "A 52-year-old woman with a 5-year history of Primary Biliary Cholangitis presents with new-onset ascites and hepatic encephalopathy. Her Model for End-Stage Liver Disease (MELD) score is 22. Liver biopsy shows extensive fibrosis with regenerative nodules. She has been compliant with ursodeoxycholic acid therapy.",
                "question": "Which of the following is the most appropriate next step in management?",
                "choices": {
                    "A": "Increase the dose of ursodeoxycholic acid",
                    "B": "Add obeticholic acid to her regimen",
                    "C": "Refer for liver transplantation evaluation",
                    "D": "Start immunosuppressive therapy with prednisone",
                    "E": "Perform transjugular intrahepatic portosystemic shunt (TIPS)",
                },
                "correct_answer": "C",
                "explanation": "This patient has progressed to decompensated cirrhosis despite medical therapy, as evidenced by ascites, hepatic encephalopathy, and biopsy showing cirrhosis. With a MELD score of 22 and decompensated disease, liver transplantation evaluation is the most appropriate next step. Increasing ursodeoxycholic acid (A) or adding obeticholic acid (B) will not reverse established cirrhosis. Prednisone (D) is not indicated in PBC. TIPS (E) may help with portal hypertension complications but does not address the underlying disease progression.",
            },
        ],
    },
    {
        "objective": "Recognize the clinical features and diagnostic criteria for Autoimmune Hepatitis",
        "questions": [
            {
                "question_number": 1,
                "difficulty": "Medium",
                "vignette": "A 32-year-old woman presents with fatigue, jaundice, and right upper quadrant discomfort for 3 weeks. She has a history of Hashimoto's thyroiditis. Physical examination shows hepatomegaly. Laboratory studies reveal: AST: 890 U/L, ALT: 1,120 U/L, Total bilirubin: 4.8 mg/dL, ALP: 145 U/L, IgG: 2,800 mg/dL (normal: 700-1,600 mg/dL). Anti-smooth muscle antibody is positive at 1:320.",
                "question": "Which of the following histologic findings would most likely be seen on liver biopsy?",
                "choices": {
                    "A": "Florid duct lesion with granulomatous inflammation",
                    "B": "Interface hepatitis with plasma cell infiltration",
                    "C": "Macrovesicular steatosis with Mallory-Denk bodies",
                    "D": "Centrilobular necrosis with minimal inflammation",
                    "E": "Onion-skin fibrosis around bile ducts",
                },
                "correct_answer": "B",
                "explanation": "This patient has classic features of autoimmune hepatitis: young woman with another autoimmune disease, marked transaminase elevation, hypergammaglobulinemia (elevated IgG), and positive anti-smooth muscle antibody. The characteristic histologic finding is interface hepatitis (inflammation at the portal-parenchymal interface) with plasma cell infiltration. Option A describes PBC. Option C describes alcoholic hepatitis. Option D describes ischemic hepatitis. Option E describes primary sclerosing cholangitis.",
            },
            {
                "question_number": 2,
                "difficulty": "Medium",
                "vignette": "A 45-year-old woman is diagnosed with autoimmune hepatitis based on clinical presentation, elevated IgG, positive ANA and anti-smooth muscle antibodies, and liver biopsy showing interface hepatitis. She has no contraindications to immunosuppressive therapy.",
                "question": "Which of the following is the most appropriate initial treatment regimen?",
                "choices": {
                    "A": "Ursodeoxycholic acid alone",
                    "B": "Prednisone plus azathioprine",
                    "C": "Methotrexate alone",
                    "D": "Mycophenolate mofetil alone",
                    "E": "Tacrolimus plus prednisone",
                },
                "correct_answer": "B",
                "explanation": "The standard initial treatment for autoimmune hepatitis is combination therapy with prednisone and azathioprine. This regimen allows for lower steroid doses while maintaining efficacy. Ursodeoxycholic acid (A) is used for PBC, not autoimmune hepatitis. Methotrexate (C) and mycophenolate (D) are second-line agents. Tacrolimus (E) is not first-line therapy for autoimmune hepatitis.",
            },
        ],
    },
    {
        "objective": "Differentiate between primary sclerosing cholangitis and other cholestatic liver diseases",
        "questions": [
            {
                "question_number": 1,
                "difficulty": "Hard",
                "vignette": "A 38-year-old man with a 10-year history of ulcerative colitis presents with fatigue, pruritus, and intermittent right upper quadrant pain. Laboratory studies show: ALP: 380 U/L, GGT: 290 U/L, Total bilirubin: 1.8 mg/dL, AST: 78 U/L, ALT: 85 U/L. Anti-mitochondrial antibody is negative. MRCP shows multifocal strictures and dilatations of the intrahepatic and extrahepatic bile ducts with a 'beaded' appearance.",
                "question": "Which of the following complications is this patient at highest risk for developing?",
                "choices": {
                    "A": "Hepatocellular carcinoma only",
                    "B": "Cholangiocarcinoma",
                    "C": "Autoimmune hemolytic anemia",
                    "D": "Renal tubular acidosis",
                    "E": "Pulmonary hypertension",
                },
                "correct_answer": "B",
                "explanation": "This patient has primary sclerosing cholangitis (PSC), as indicated by the association with ulcerative colitis, cholestatic liver enzymes, negative AMA, and characteristic MRCP findings of multifocal biliary strictures. PSC carries a 10-15% lifetime risk of cholangiocarcinoma, which is the most feared complication. While HCC (A) can occur, cholangiocarcinoma is more common. Options C, D, and E are not specifically associated with PSC.",
            }
        ],
    },
]


def main():
    # Set up Jinja2 environment
    template_path = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(
        loader=FileSystemLoader(template_path), autoescape=select_autoescape()
    )
    template = env.get_template("vignette.html")

    # Render the template with mock data
    html = template.render(learning_objectives=mock_learning_objectives)

    # Save HTML for debugging
    html_output_path = os.path.join("data", "output", "test_vignette.html")
    os.makedirs(os.path.dirname(html_output_path), exist_ok=True)
    with open(html_output_path, "w") as f:
        f.write(html)
    print(f"HTML saved to: {html_output_path}")

    # Generate PDF
    pdf_output_path = os.path.join("data", "output", "test_vignette.pdf")
    with open(pdf_output_path, "wb") as f:
        pisa_status = pisa.CreatePDF(html, dest=f)
        if hasattr(pisa_status, "err") and getattr(pisa_status, "err", None):
            print("Error generating PDF")
            return

    print(f"PDF saved to: {pdf_output_path}")

    # Open the PDF
    import subprocess

    subprocess.run(["open", pdf_output_path])


if __name__ == "__main__":
    main()
    main()
