(() => {
  const { fmt, Reactor } = Nuxiva;
  const $ = (id) => document.getElementById(id);

  const canvas = $("reactor-canvas");
  const reactor = new Reactor(canvas);

  let state = null;
  let selectedLang = "it";

  setInterval(() => {
    $("clock").textContent = fmt.clock();
  }, 1000);

  function hideAllStages() {
    ["stage-language", "stage-choice", "stage-progress", "stage-failure"].forEach((id) => {
      const el = $(id);
      if (el) el.hidden = true;
    });
  }

  function showStage(stageId) {
    hideAllStages();
    const el = $(stageId);
    if (el) el.hidden = false;
  }

  async function fetchState() {
    try {
      const res = await fetch("/api/activation/state", { cache: "no-store" });
      if (!res.ok) return;
      state = await res.json();
      render();
    } catch {
      // Global network handling
    }
  }

  function render() {
    if (!state) return;

    const pct = Math.min(100, Math.max(0, state.percent || 0));
    $("progress-pct").textContent = `${pct}%`;
    reactor.set(pct / 100);

    if (state.stage === "new" || state.stage === "language") {
      showStage("stage-language");
      $("current-title").setAttribute("data-i18n", "choose_language");
      return;
    }

    if (state.stage === "awaiting_user") {
      showStage("stage-choice");
      renderChoice(state.current);
      return;
    }

    if (state.stage === "failed") {
      showStage("stage-failure");
      const err = (state.progress[state.current] || {}).error || "";
      $("failure-msg").textContent = err;
      return;
    }

    if (state.stage === "running") {
      showStage("stage-progress");
      $("win-seq-name").textContent = state.current || "processing";
      advancePipeline();
    }
  }

  async function renderChoice(sequenceId) {
    $("choice-title").textContent = sequenceId;
    const cardsEl = $("choice-cards");
    cardsEl.innerHTML = "";

    const cardYes = document.createElement("div");
    cardYes.className = "choice-card recommended";
    cardYes.innerHTML = `<h3>Installare ora</h3><p>Procedi con l'installazione locale completa</p>`;
    cardYes.onclick = () => submitUserChoice(sequenceId, "yes");

    const cardNo = document.createElement("div");
    cardNo.className = "choice-card";
    cardNo.innerHTML = `<h3>Non ora</h3><p>Configura o installa in un secondo momento</p>`;
    cardNo.onclick = () => submitUserChoice(sequenceId, "no");

    cardsEl.appendChild(cardYes);
    cardsEl.appendChild(cardNo);
  }

  async function submitUserChoice(sequenceId, choiceId) {
    try {
      const res = await fetch(`/api/activation/choice/${sequenceId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice: choiceId }),
      });
      if (res.ok) {
        state = await res.json();
        render();
        advancePipeline();
      }
    } catch {
      // Network handler
    }
  }

  async function advancePipeline() {
    try {
      const res = await fetch("/api/activation/advance", { method: "POST" });
      if (res.ok) {
        state = await res.json();
        render();
      }
    } catch {
      // Network handler
    }
  }

  $("btn-start").onclick = async () => {
    advancePipeline();
  };

  $("btn-retry").onclick = async () => {
    advancePipeline();
  };

  $("btn-reset").onclick = async () => {
    try {
      const res = await fetch("/api/activation/reset", { method: "POST" });
      if (res.ok) {
        state = await res.json();
        render();
      }
    } catch {
      // Network handler
    }
  };

  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".lang-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedLang = btn.dataset.lang;
    };
  });

  fetchState();
  setInterval(fetchState, 3000);
})();
