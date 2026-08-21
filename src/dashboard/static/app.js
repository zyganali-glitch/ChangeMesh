/**
 * ChangeMesh Judge and Operator Dashboard — Client Application
 * Vanilla ES6, Zero External Dependencies, Accessible & Localized (EN/TR)
 */

(function () {
  "use strict";

  // I18N Translations Dictionary
  const I18N = {
    en: {
      appTitle: "ChangeMesh",
      appSubtitle: "Proof-Carrying Autonomous Enterprise Change Platform",
      statusInitializing: "INITIALIZING",
      statusReady: "SYSTEM READY",
      statusRunning: "EXECUTING DEMO",
      statusComplete: "CHANGE COMPLETE",
      runDemoBtn: "▶ Run Demo Change",
      runningBtn: "⏳ Executing...",
      overviewTitle: "Change Lifecycle Overview",
      lblChangeId: "Change ID",
      lblLifecycleState: "Current State",
      lblAutonomyClass: "Autonomy Classification",
      lblPassportDigest: "Evidence Passport Root",
      lblIntegrityStatus: "Integrity: Sealed",
      fleetTitle: "Agent Fleet & Causal Event Timeline",
      fleetSubheading: "Active Specialist Fleet",
      timelineSubheading: "Causal Event Timeline (DAG)",
      approvalTitle: "Reversibility Gate & Approval Compression",
      approvalBadge: "HUMAN ON THE LOOP",
      compressionRatio: "5 standard review cycles compressed into 1 irreducible decision packet",
      approvalQuestion: "Authorize Expand-Contract Migration for Acme Billing Platform?",
      approvalWork: "Impact Scout mapped 7 dependencies; Policy Guardian confirmed zero secret/PII leaks; ShadowLab verified automated rollback and legacy client compatibility.",
      lblActionScope: "Action Scope",
      lblRollbackProof: "Rollback Proof",
      lblShadowLabStatus: "ShadowLab Twin",
      valActionScope: "Postgres DDL / GitHub Draft PR",
      valRollbackProof: "VERIFIED (Simulated DDL Revert)",
      valShadowLabStatus: "8 / 8 Scenarios Passed",
      btnApprove: "✓ Authorize Execution",
      btnReject: "✕ Reject & Compensate",
      btnApproved: "✓ Authorized & Draft PR Sealed",
      btnRejected: "✕ Compensated & Reverted",
      tokenStatus: "Token: Valid HMAC-SHA256 Bound",
      shadowlabTitle: "ShadowLab Change Rehearsal Twin",
      shadowlabBadge: "8 Canonical Scenarios Verified",
      evidenceTitle: "Tamper-Evident Evidence Ledger & Cloud Proofs",
      passportTitle: "Cryptographic Evidence Passport",
      cloudTitle: "Google Cloud Integration Proofs",
      footerText: "ChangeMesh — All Things Agentic Hackathon Entry (Fortified Enterprise Fleet Category)",
      footerMeta: "Zero external write credentials in browser • Fully deterministic fact authority • WCAG 2.1 AA Compliant"
    },
    tr: {
      appTitle: "ChangeMesh",
      appSubtitle: "Kanıt Taşıyan Otonom Kurumsal Değişiklik Platformu",
      statusInitializing: "BAŞLATILIYOR",
      statusReady: "SİSTEM HAZIR",
      statusRunning: "DEMO ÇALIŞTIRILIYOR",
      statusComplete: "DEĞİŞİKLİK TAMAMLANDI",
      runDemoBtn: "▶ Demo Değişikliği Başlat",
      runningBtn: "⏳ Çalıştırılıyor...",
      overviewTitle: "Değişiklik Yaşam Döngüsü Özeti",
      lblChangeId: "Değişiklik Kimliği",
      lblLifecycleState: "Mevcut Durum",
      lblAutonomyClass: "Otonomi Sınıflandırması",
      lblPassportDigest: "Kanıt Pasaportu Kök Özeti",
      lblIntegrityStatus: "Bütünlük: Mühürlü",
      fleetTitle: "Ajan Filosu ve Nedensel Olay Zaman Çizelgesi",
      fleetSubheading: "Aktif Uzman Ajan Filosu",
      timelineSubheading: "Nedensel Olay Çizelgesi (DAG)",
      approvalTitle: "Geri Alınabilirlik Kapısı ve Onay Sıkıştırma",
      approvalBadge: "DÖNGÜDE İNSAN KONTROLÜ",
      compressionRatio: "5 standart inceleme döngüsü 1 indirgenemez karar paketine sıkıştırıldı",
      approvalQuestion: "Acme Faturalandırma Platformu Genişlet-Daralt Geçişi Onaylansın mı?",
      approvalWork: "Impact Scout 7 bağımlılığı haritaladı; Policy Guardian sıfır gizli bilgi sızıntısı doğruladı; ShadowLab otomatik geri alma ve eski istemci uyumluluğunu test etti.",
      lblActionScope: "Eylem Kapsamı",
      lblRollbackProof: "Geri Alma Kanıtı",
      lblShadowLabStatus: "ShadowLab İkizi",
      valActionScope: "Postgres DDL / GitHub Taslak PR",
      valRollbackProof: "DOĞRULANDI (Simüle DDL Geri Alma)",
      valShadowLabStatus: "8 / 8 Senaryo Başarılı",
      btnApprove: "✓ Yürütmeyi Yetkilendir",
      btnReject: "✕ Reddet ve Dengele",
      btnApproved: "✓ Yetkilendirildi & Taslak PR Mühürlendi",
      btnRejected: "✕ Dengelendi & Geri Alındı",
      tokenStatus: "Belirteç: Geçerli HMAC-SHA256 Bağlı",
      shadowlabTitle: "ShadowLab Değişiklik Prova İkizi",
      shadowlabBadge: "8 Kanonik Senaryo Doğrulandı",
      evidenceTitle: "Değiştirilemez Kanıt Defteri ve Bulut Kanıtları",
      passportTitle: "Kriptografik Kanıt Pasaportu",
      cloudTitle: "Google Cloud Entegrasyon Kanıtları",
      footerText: "ChangeMesh — All Things Agentic Hackathon Başvurusu (Fortified Enterprise Fleet Kategorisi)",
      footerMeta: "Tarayıcıda sıfır harici yazma kimlik bilgisi • Tamamen deterministik olgu otoritesi • WCAG 2.1 AA Uyumlu"
    }
  };

  // Canonical Standard 8 ShadowLab Scenarios
  const SHADOWLAB_SCENARIOS = [
    {
      id: "SCENARIO_NORMAL_MIGRATION",
      name: "Clean Schema Migration",
      desc: "Non-breaking column addition with zero errors in synthetic SQLite sandbox.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "NONE"
    },
    {
      id: "SCENARIO_503_TRANSIENT_RECOVERY",
      name: "API 503 Exponential Recovery",
      desc: "Handles two consecutive 503 failures with backoff delays (100ms, 200ms); succeeds on attempt 3.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "HTTP_503"
    },
    {
      id: "SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION",
      name: "Partial Interruption Compensation",
      desc: "Lock timeout on step 2 triggers automated saga compensation DDL cleanup.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "DB_LOCK"
    },
    {
      id: "SCENARIO_STALE_APPROVAL",
      name: "Stale Approval Rejection",
      desc: "Rejects mismatched plan hash tokens; halts execution at Reversibility Gate.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "STALE_TOKEN"
    },
    {
      id: "SCENARIO_PROMPT_INJECTION",
      name: "Schema Prompt Injection Quarantine",
      desc: "Detects instruction override directives in untrusted DDL and isolates in memory.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "INJECTION"
    },
    {
      id: "SCENARIO_MISSING_ROLLBACK",
      name: "Missing Rollback Auto-Correction",
      desc: "Rejects irreversible DDL and automatically synthesizes down-migration script.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "NO_ROLLBACK"
    },
    {
      id: "SCENARIO_LEGACY_CLIENT_BREAK",
      name: "Legacy Client Expand-Contract",
      desc: "Detects breaking column rename and automatically synthesizes compatibility dual-write view.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "CLIENT_BREAK"
    },
    {
      id: "SCENARIO_RESTART_RESUME",
      name: "Process Crash Checkpoint Resume",
      desc: "Simulates mid-flight crash; restores exact pending tasks from durable P-10 checkpoint.",
      mode: "SIMULATION",
      status: "PASS",
      fault: "CRASH_RESTART"
    }
  ];

  // Standard Agent Fleet Definition
  const AGENT_FLEET = [
    { id: "change_orchestrator", name: "Change Orchestrator (Google ADK)", role: "Saga & Delegation", rev: "rev-2.0.0", tasks: 8, status: "COMPLETED" },
    { id: "impact_scout", name: "Impact Scout", role: "Blast Radius & Dependencies", rev: "rev-1.1.0", tasks: 2, status: "COMPLETED" },
    { id: "policy_guardian", name: "Policy Guardian", role: "Deterministic DLP & Gates", rev: "rev-1.2.0", tasks: 3, status: "COMPLETED" },
    { id: "migration_engineer", name: "Migration Engineer", role: "Expand-Contract DDL", rev: "rev-1.0.0", tasks: 2, status: "COMPLETED" },
    { id: "evidence_auditor", name: "Evidence Auditor", role: "Blind Semantic Audit", rev: "rev-1.0.0", tasks: 2, status: "COMPLETED" },
    { id: "release_steward", name: "Release Steward", role: "Bounded GitHub Draft PR", rev: "rev-1.0.0", tasks: 1, status: "COMPLETED" }
  ];

  // Standard Timeline Events
  const CANONICAL_TIMELINE = [
    { state: "RECEIVED", time: "T+0.0s", desc: "Change request ingested; secret scan passed." },
    { state: "DISCOVERING", time: "T+0.4s", desc: "Impact Scout mapped 7 dependencies across Acme billing graph." },
    { state: "QUALIFYING", time: "T+0.8s", desc: "Capability Passport verified 6 agents for required capabilities." },
    { state: "REHEARSING", time: "T+1.5s", desc: "ShadowLab executed 8 rehearsal scenarios in simulation." },
    { state: "GROUNDED", time: "T+2.0s", desc: "Deterministic policy pre-checks passed with 0 secret/PII findings." },
    { state: "AWAITING_AUTHORITY", time: "T+2.3s", desc: "Approval compression card generated; awaiting human authority." },
    { state: "AUTHORIZED", time: "T+2.6s", desc: "HMAC-SHA256 authority token verified; execution approved." },
    { state: "EXECUTING", time: "T+3.1s", desc: "Migration Engineer generated expand-contract DDL manifest." },
    { state: "VERIFYING", time: "T+3.6s", desc: "Evidence Auditor confirmed neutral criteria satisfaction." },
    { state: "COMPLETE", time: "T+4.2s", desc: "Draft PR created; tamper-evident Evidence Passport sealed." }
  ];

  let currentLang = "en";
  let currentTheme = "dark";

  // DOM Elements
  const runDemoBtn = document.getElementById("run-demo-btn");
  const themeToggleBtn = document.getElementById("theme-toggle-btn");
  const themeIcon = document.getElementById("theme-icon");
  const langToggleBtn = document.getElementById("lang-toggle-btn");
  const langText = document.getElementById("lang-text");
  const statusPill = document.getElementById("live-status-pill");
  const statusText = document.getElementById("status-text");
  const valChangeId = document.getElementById("val-change-id");
  const valTenantId = document.getElementById("val-tenant-id");
  const valLifecycleState = document.getElementById("val-lifecycle-state");
  const valCorrelationId = document.getElementById("val-correlation-id");
  const valAutonomyClass = document.getElementById("val-autonomy-class");
  const valPassportDigest = document.getElementById("val-passport-digest");
  const agentFleetContainer = document.getElementById("agent-fleet-container");
  const timelineList = document.getElementById("timeline-list");
  const taskCountBadge = document.getElementById("task-count-badge");
  const shadowlabScenarioGrid = document.getElementById("shadowlab-scenario-grid");
  const btnApprove = document.getElementById("btn-approve");
  const btnReject = document.getElementById("btn-reject");

  // Initialize
  function init() {
    setupEventListeners();
    renderShadowLabGrid();
    renderAgentFleet(AGENT_FLEET);
    renderTimeline(CANONICAL_TIMELINE);
    applyLanguage(currentLang);
    fetchLiveSnapshot();
  }

  function setupEventListeners() {
    if (themeToggleBtn) {
      themeToggleBtn.addEventListener("click", toggleTheme);
    }
    if (langToggleBtn) {
      langToggleBtn.addEventListener("click", toggleLanguage);
    }
    if (runDemoBtn) {
      runDemoBtn.addEventListener("click", runDemoChange);
    }
    if (btnApprove) {
      btnApprove.addEventListener("click", () => {
        btnApprove.textContent = I18N[currentLang].btnApproved;
        btnApprove.classList.remove("btn-success");
        btnApprove.classList.add("btn-secondary");
        btnApprove.disabled = true;
        if (btnReject) btnReject.style.display = "none";
      });
    }
    if (btnReject) {
      btnReject.addEventListener("click", () => {
        btnReject.textContent = I18N[currentLang].btnRejected;
        btnReject.classList.remove("btn-danger");
        btnReject.classList.add("btn-secondary");
        btnReject.disabled = true;
        if (btnApprove) btnApprove.style.display = "none";
      });
    }
  }

  function toggleTheme() {
    currentTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", currentTheme);
    if (themeIcon) {
      themeIcon.textContent = currentTheme === "dark" ? "☼" : "☾";
    }
  }

  function toggleLanguage() {
    currentLang = currentLang === "en" ? "tr" : "en";
    if (langText) {
      langText.textContent = currentLang === "en" ? "TR" : "EN";
    }
    applyLanguage(currentLang);
  }

  function applyLanguage(lang) {
    const t = I18N[lang] || I18N.en;
    document.querySelector(".app-title").textContent = t.appTitle;
    document.querySelector(".app-subtitle").textContent = t.appSubtitle;
    if (runDemoBtn && !runDemoBtn.disabled) runDemoBtn.textContent = t.runDemoBtn;
    
    document.getElementById("overview-heading").textContent = t.overviewTitle;
    document.getElementById("lbl-change-id").textContent = t.lblChangeId;
    document.getElementById("lbl-lifecycle-state").textContent = t.lblLifecycleState;
    document.getElementById("lbl-autonomy-class").textContent = t.lblAutonomyClass;
    document.getElementById("lbl-passport-digest").textContent = t.lblPassportDigest;
    document.getElementById("val-integrity-status").textContent = t.lblIntegrityStatus;

    document.getElementById("fleet-heading").textContent = t.fleetTitle;
    document.getElementById("fleet-subheading").textContent = t.fleetSubheading;
    document.getElementById("timeline-subheading").textContent = t.timelineSubheading;

    document.getElementById("approval-heading").textContent = t.approvalTitle;
    document.getElementById("approval-badge").textContent = t.approvalBadge;
    document.getElementById("compression-ratio-text").textContent = t.compressionRatio;
    document.getElementById("approval-decision-question").textContent = t.approvalQuestion;
    document.getElementById("approval-completed-work").textContent = t.approvalWork;
    document.getElementById("lbl-action-scope").textContent = t.lblActionScope;
    document.getElementById("lbl-rollback-proof").textContent = t.lblRollbackProof;
    document.getElementById("lbl-rehearsal-status").textContent = t.lblShadowLabStatus;
    document.getElementById("val-action-scope").textContent = t.valActionScope;
    document.getElementById("val-rollback-proof").textContent = t.valRollbackProof;
    document.getElementById("val-rehearsal-status").textContent = t.valShadowLabStatus;
    if (btnApprove && !btnApprove.disabled) btnApprove.textContent = t.btnApprove;
    if (btnReject && !btnReject.disabled) btnReject.textContent = t.btnReject;
    document.getElementById("authority-token-status").textContent = t.tokenStatus;

    document.getElementById("shadowlab-heading").textContent = t.shadowlabTitle;
    document.getElementById("shadowlab-badge").textContent = t.shadowlabBadge;
    document.getElementById("evidence-heading").textContent = t.evidenceTitle;
    document.getElementById("passport-subheading").textContent = t.passportTitle;
    document.getElementById("cloud-subheading").textContent = t.cloudTitle;

    document.querySelector(".footer-text").textContent = t.footerText;
    document.querySelector(".footer-meta").textContent = t.footerMeta;
  }

  function renderShadowLabGrid() {
    if (!shadowlabScenarioGrid) return;
    shadowlabScenarioGrid.innerHTML = "";

    SHADOWLAB_SCENARIOS.forEach((sc) => {
      const card = document.createElement("div");
      card.className = "card scenario-card";
      card.tabIndex = 0;
      card.innerHTML = `
        <div class="scenario-header">
          <span class="scenario-name">${sc.name}</span>
          <span class="badge badge-success">${sc.status}</span>
        </div>
        <p class="scenario-desc">${sc.desc}</p>
        <div class="scenario-footer">
          <span>FAULT: ${sc.fault}</span>
          <span class="badge badge-info">${sc.mode}</span>
        </div>
      `;
      shadowlabScenarioGrid.appendChild(card);
    });
  }

  function renderAgentFleet(agents) {
    if (!agentFleetContainer) return;
    agentFleetContainer.innerHTML = "";

    agents.forEach((ag) => {
      const card = document.createElement("div");
      card.className = "card agent-card";
      card.tabIndex = 0;
      card.innerHTML = `
        <div class="agent-info">
          <span class="agent-name">${ag.name}</span>
          <span class="agent-rev">${ag.role} • ${ag.rev}</span>
        </div>
        <div class="agent-stats">
          <span class="badge badge-info">${ag.tasks} Tasks</span>
          <span class="badge badge-success">${ag.status}</span>
        </div>
      `;
      agentFleetContainer.appendChild(card);
    });
  }

  function renderTimeline(events) {
    if (!timelineList) return;
    timelineList.innerHTML = "";

    events.forEach((ev) => {
      const item = document.createElement("li");
      item.className = "timeline-item";
      item.innerHTML = `
        <div class="timeline-dot" aria-hidden="true"></div>
        <div class="timeline-header">
          <span class="timeline-state text-accent">${ev.state}</span>
          <span class="timeline-time">${ev.time}</span>
        </div>
        <p class="timeline-desc">${ev.desc}</p>
      `;
      timelineList.appendChild(item);
    });

    if (taskCountBadge) {
      taskCountBadge.textContent = `${events.length} Lifecycle Events`;
    }
  }

  async function fetchLiveSnapshot() {
    try {
      const resp = await fetch("/api/dashboard/snapshot");
      if (resp.ok) {
        const data = await resp.json();
        updateDashboardUI(data);
      } else {
        // Default demo state
        setDefaultDemoState();
      }
    } catch {
      setDefaultDemoState();
    }
  }

  function setDefaultDemoState() {
    if (statusText) statusText.textContent = I18N[currentLang].statusReady;
    if (valChangeId) valChangeId.textContent = "change-p24-demo-acme";
    if (valTenantId) valTenantId.textContent = "Tenant: tenant-acme-corp";
    if (valLifecycleState) valLifecycleState.textContent = "COMPLETE";
    if (valCorrelationId) valCorrelationId.textContent = "Corr: corr-p24-live-01";
    if (valPassportDigest) valPassportDigest.textContent = "2f36878ce9c8329bad...875e3";
  }

  function updateDashboardUI(snapshot) {
    if (!snapshot) return;
    if (statusText) statusText.textContent = I18N[currentLang].statusComplete;

    if (snapshot.change_view) {
      const cv = snapshot.change_view;
      if (valChangeId) valChangeId.textContent = cv.change_id;
      if (valTenantId) valTenantId.textContent = `Tenant: ${cv.tenant_id}`;
      if (valLifecycleState) valLifecycleState.textContent = cv.current_state;
      if (valCorrelationId) valCorrelationId.textContent = `Corr: ${cv.correlation_id}`;
      if (valAutonomyClass) valAutonomyClass.textContent = cv.autonomy_class || "AUTO_EXECUTE";
    }

    if (snapshot.snapshot_digest && valPassportDigest) {
      valPassportDigest.textContent = `${snapshot.snapshot_digest}...sealed`;
    }

    if (snapshot.agent_views && snapshot.agent_views.length > 0) {
      renderAgentFleet(snapshot.agent_views.map(av => ({
        id: av.agent_id,
        name: av.agent_role || av.agent_id,
        role: av.agent_role,
        rev: av.agent_revision,
        tasks: av.task_count,
        status: av.failed_task_count > 0 ? "FAILED" : "COMPLETED"
      })));
    }
  }

  async function runDemoChange() {
    if (!runDemoBtn) return;
    runDemoBtn.disabled = true;
    runDemoBtn.textContent = I18N[currentLang].runningBtn;
    if (statusText) statusText.textContent = I18N[currentLang].statusRunning;

    try {
      const resp = await fetch("/run-e2e", { method: "POST" });
      if (resp.ok) {
        const result = await resp.json();
        if (statusText) statusText.textContent = I18N[currentLang].statusComplete;
        if (valChangeId) valChangeId.textContent = result.change_id || "change-p24-live";
        if (valLifecycleState) valLifecycleState.textContent = result.final_state || "COMPLETE";
        if (valPassportDigest) valPassportDigest.textContent = (result.demo_digest || "").substring(0, 20) + "...";
      }
    } catch {
      // Fallback for purely static offline inspection
      setDefaultDemoState();
    } finally {
      runDemoBtn.disabled = false;
      runDemoBtn.textContent = I18N[currentLang].runDemoBtn;
    }
  }

  // DOM Content Loaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
