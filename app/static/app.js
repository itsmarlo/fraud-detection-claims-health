const byId = (id) => document.getElementById(id);
const form = byId("claim-form");
const submitButton = form.querySelector("button[type='submit']");

const componentNames = {
  eligibility: "Eligibility",
  member_history: "Member history",
  incident_type: "Service context",
  document_validation: "Document consistency",
  provider_network: "Provider and network",
  policy_beneficiary: "Policy and beneficiary",
};

function value(id) { return byId(id).value.trim(); }
function numberValue(id) { return Number(byId(id).value || 0); }
function checked(id) { return byId(id).checked; }
function optionalDate(id) { return value(id) || null; }
function codeList(id) { return value(id).split(",").map((code) => code.trim()).filter(Boolean); }

function buildPayload() {
  return {
    claim_id: value("claim_id"),
    policy_id: value("policy_id"),
    member_id: value("member_id"),
    provider_id: value("provider_id"),
    claim_type: value("claim_type"),
    cause_of_loss: value("cause_of_loss"),
    claim_amount: numberValue("claim_amount"),
    billed_amount: numberValue("billed_amount"),
    allowed_amount: numberValue("allowed_amount"),
    policy_start_date: value("policy_start_date"),
    policy_end_date: value("policy_end_date"),
    date_of_loss: value("date_of_loss"),
    claim_submission_date: value("claim_submission_date"),
    coverage_upgrade_date: optionalDate("coverage_upgrade_date"),
    beneficiary_added_date: optionalDate("beneficiary_added_date"),
    previous_claims_last_12_months: numberValue("previous_claims_last_12_months"),
    provider_claims_last_90_days: 0,
    provider_peer_volume_percentile: value("provider_peer_volume_percentile") ? numberValue("provider_peer_volume_percentile") : null,
    provider_suspicious_claims_last_12_months: numberValue("provider_suspicious_claims_last_12_months"),
    diagnosis_codes: codeList("diagnosis_codes"),
    procedure_codes: codeList("procedure_codes"),
    provider_specialty: value("provider_specialty") || null,
    diagnosis_procedure_mismatch: checked("diagnosis_procedure_mismatch"),
    provider_specialty_mismatch: checked("provider_specialty_mismatch"),
    newly_added_beneficiary: checked("newly_added_beneficiary"),
    high_value_claim: numberValue("claim_amount") >= 3000,
    documents: {
      hospital_bill: checked("hospital_bill"),
      discharge_summary: checked("discharge_summary"),
      medical_report: checked("medical_report"),
      lab_or_test_results: checked("lab_or_test_results"),
      duplicate_document_found: checked("duplicate_document_found"),
      low_resolution_image: checked("low_resolution_image"),
      treatment_date: optionalDate("treatment_date"),
      admission_date: optionalDate("admission_date"),
      discharge_date: optionalDate("discharge_date"),
    },
  };
}

function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function tierClass(tier) {
  if (tier.startsWith("ROUTINE")) return "routine";
  if (tier.startsWith("ELEVATED")) return "elevated";
  if (tier.startsWith("HIGH")) return "high";
  return "urgent";
}

function readableTier(tier) {
  return tier.toLowerCase().replaceAll("_", " ").replace("review priority", "priority");
}

function renderReasons(reasons) {
  const list = byId("reason-list");
  clearNode(list);
  byId("reason-count").textContent = `${reasons.length} ${reasons.length === 1 ? "signal" : "signals"}`;
  if (!reasons.length) {
    list.append(element("p", "muted", "No deterministic risk signals were triggered."));
    return;
  }
  reasons.forEach((reason) => {
    const card = element("article", "reason");
    const top = element("div", "reason-top");
    top.append(element("span", "reason-code", reason.code));
    top.append(element("span", "severity", reason.severity));
    card.append(top, element("p", "", reason.message));
    const refs = element("div", "refs");
    reason.evidence_refs.forEach((ref) => refs.append(element("span", "ref", ref)));
    card.append(refs);
    list.append(card);
  });
}

function renderComponents(components) {
  const list = byId("component-list");
  clearNode(list);
  Object.entries(components).forEach(([key, score]) => {
    const row = element("div", "component-row");
    const label = element("div");
    label.append(element("span", "", componentNames[key] || key), element("strong", "", `${Math.round(score)}`));
    const track = element("div", "component-track");
    const bar = element("span");
    bar.style.width = `${score}%`;
    track.append(bar);
    row.append(label, track);
    list.append(row);
  });
}

function renderWarnings(warnings) {
  const section = byId("warnings-section");
  const list = byId("warning-list");
  clearNode(list);
  section.classList.toggle("hidden", !warnings.length);
  warnings.forEach((warning) => list.append(element("li", "", warning)));
}

function renderAssessment(result) {
  byId("empty-result").classList.add("hidden");
  byId("error-state").classList.add("hidden");
  byId("assessment").classList.remove("hidden");
  byId("result-claim-id").textContent = result.claim_id;
  byId("risk-score").textContent = Math.round(result.risk_score);
  byId("recommended-action").textContent = result.recommended_action;
  byId("confidence-score").textContent = `${Math.round(result.confidence_score)}%`;
  byId("confidence-bar").style.width = `${result.confidence_score}%`;
  byId("version-line").textContent = `${result.rule_set_version} · ${result.schema_version}`;

  const badge = byId("tier-badge");
  badge.className = `tier-badge ${tierClass(result.risk_tier)}`;
  badge.textContent = readableTier(result.risk_tier);

  const ring = byId("score-ring");
  ring.style.setProperty("--score", result.risk_score);
  const colors = { routine: "#0c7a64", elevated: "#7b8122", high: "#b86612", urgent: "#a33c32" };
  ring.style.setProperty("--score-color", colors[tierClass(result.risk_tier)]);

  renderReasons(result.reasons);
  renderComponents(result.component_scores);
  renderWarnings(result.warnings);
  if (window.innerWidth < 1080) byId("result-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function showError(message) {
  byId("empty-result").classList.add("hidden");
  byId("assessment").classList.add("hidden");
  byId("error-state").classList.remove("hidden");
  byId("error-message").textContent = message;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  submitButton.disabled = true;
  submitButton.firstElementChild.textContent = "Assessing…";
  try {
    const response = await fetch("/api/v1/healthcare-claims/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const result = await response.json();
    if (!response.ok) {
      const details = Array.isArray(result.detail) ? result.detail.map((item) => item.msg).join(" ") : result.detail;
      throw new Error(details || "The service returned an unexpected response.");
    }
    renderAssessment(result);
  } catch (error) {
    showError(error.message || "Check that the service is running, then try again.");
  } finally {
    submitButton.disabled = false;
    submitButton.firstElementChild.textContent = "Run assessment";
  }
});

const samples = {
  routine: {
    claim_id: "CLM-ROUTINE-1001", member_id: "MBR-ROUTINE", provider_id: "NPI-ROUTINE", policy_id: "POL-ROUTINE",
    claim_type: "OUT_PATIENT", cause_of_loss: "ROUTINE_CONSULTATION", claim_amount: 250, billed_amount: 300, allowed_amount: 200,
    policy_start_date: "2025-01-01", policy_end_date: "2027-12-31", date_of_loss: "2026-05-01", claim_submission_date: "2026-05-02",
    coverage_upgrade_date: "", beneficiary_added_date: "", diagnosis_codes: "Z00.0", procedure_codes: "99213", provider_specialty: "Primary care",
    previous_claims_last_12_months: 0, provider_suspicious_claims_last_12_months: 0, provider_peer_volume_percentile: 45,
    diagnosis_procedure_mismatch: false, provider_specialty_mismatch: false, newly_added_beneficiary: false,
    hospital_bill: true, discharge_summary: false, medical_report: true, lab_or_test_results: false, duplicate_document_found: false, low_resolution_image: false,
    treatment_date: "2026-05-01", admission_date: "", discharge_date: "",
  },
  priority: {
    claim_id: "CLM-1001", member_id: "MBR-1234", provider_id: "NPI-456789", policy_id: "POL-9001",
    claim_type: "HOSPITAL", cause_of_loss: "ELECTIVE_PROCEDURE", claim_amount: 7500, billed_amount: 8200, allowed_amount: 6000,
    policy_start_date: "2026-01-01", policy_end_date: "2026-12-31", date_of_loss: "2026-01-18", claim_submission_date: "2026-01-25",
    coverage_upgrade_date: "2026-01-05", beneficiary_added_date: "2026-01-03", diagnosis_codes: "M54.5", procedure_codes: "99285, 72148", provider_specialty: "Orthopedics",
    previous_claims_last_12_months: 4, provider_suspicious_claims_last_12_months: 5, provider_peer_volume_percentile: 99.4,
    diagnosis_procedure_mismatch: true, provider_specialty_mismatch: false, newly_added_beneficiary: false,
    hospital_bill: true, discharge_summary: false, medical_report: false, lab_or_test_results: false, duplicate_document_found: true, low_resolution_image: true,
    treatment_date: "2026-01-18", admission_date: "2026-01-18", discharge_date: "2026-01-17",
  },
};

function loadSample(sample) {
  Object.entries(sample).forEach(([id, sampleValue]) => {
    const input = byId(id);
    if (!input) return;
    if (input.type === "checkbox") input.checked = sampleValue;
    else input.value = sampleValue;
  });
  byId("assessment").classList.add("hidden");
  byId("error-state").classList.add("hidden");
  byId("empty-result").classList.remove("hidden");
}

byId("routine-sample").addEventListener("click", () => loadSample(samples.routine));
byId("priority-sample").addEventListener("click", () => loadSample(samples.priority));
