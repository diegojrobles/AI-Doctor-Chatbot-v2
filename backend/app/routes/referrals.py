from fastapi import APIRouter, Depends, Request
from app.schemas.schemas import SymptomInput, ReferralOut
from app.services.llm_service import require_json_with_retry
from app.services.auth_service import require_clinician
from app.utils.rate_limit import limiter

router = APIRouter()


# Clinician-only. See the note in rx_draft.py -- the role was never enforced.
@router.post("/referrals", response_model=ReferralOut)
@limiter.limit("10/minute")
def route_referrals(
    request: Request, inp: SymptomInput, _user=Depends(require_clinician)
):
    def build_messages():
        system = (
            "You assist clinicians by drafting specialist referrals. "
            "JSON ONLY; no patient instructions; no dosing."
        )
        user = (
            f"Age: {inp.age}\nSymptoms: {inp.symptoms}\nConditions: {
                inp.conditions
            }\nSchema example:\n"
            + '{"suggested_specialties":[{"name":"Pulmonology","reason":"Chronic cough"}],"pre_referral_workup":["Chest X-ray","Spirometry"],"priority":"routine"}'
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    data = require_json_with_retry(build_messages)
    return ReferralOut(**data)
