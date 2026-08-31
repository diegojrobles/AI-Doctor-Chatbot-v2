from fastapi import APIRouter, Depends, Request
from app.schemas.schemas import SymptomInput, RxDraftOut
from app.services.llm_service import require_json_with_retry
from app.services.auth_service import require_clinician
from app.utils.rate_limit import limiter

router = APIRouter()


# Clinician-only, as the README has always claimed. Before this dependency the
# role was stored and signed into the JWT but never checked, so any logged-in
# patient could draft prescriptions.
@router.post("/rx_draft", response_model=RxDraftOut)
@limiter.limit("10/minute")
def route_rx(request: Request, inp: SymptomInput, _user=Depends(require_clinician)):
    def build_messages():
        system = "Clinician-only medication class draft. No dosing. JSON ONLY."
        user = (
            f"Age: {inp.age}\nSymptoms: {inp.symptoms}\nMeds: {inp.meds}\nConditions: {
                inp.conditions
            }\nSchema example:\n"
            + '{"candidates":[{"drug_class":"Inhaled corticosteroid","example":"budesonide DPI","use_case":"Persistent asthma","contraindications":["hypersensitivity"],"monitoring":["symptom diary"]}],"notes":"Draft for clinician review—do not display to patient."}'
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    data = require_json_with_retry(build_messages)
    return RxDraftOut(**data)
