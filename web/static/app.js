// Keeps the page live: snapshots arrive over Server-Sent Events every couple of
// seconds, the pump countdown ticks locally in between, and buttons post in the
// background (the next snapshot shows the result).

const $ = (id) => document.getElementById(id);
const range = $("light-range");
let pump = null; // last pump snapshot, with seconds_left counted down locally
let dragging = false;

const events = new EventSource("/events");
events.onopen = () => ($("status").textContent = "");
events.onerror = () => ($("status").textContent = "Reconnecting…");
events.onmessage = (event) => render(JSON.parse(event.data));

function render({ light, pump: latest, power, water, schedule, cycle }) {
  showSchedule(schedule);
  showCycle(cycle);
  if (!dragging) showLight(light?.value);
  pump = latest;
  showPump();
  $("power").textContent = power && !power.error
    ? `${power.BusVoltage.toFixed(1)} V · ${Math.abs(Math.round(power.BusCurrent))} mA · ${Math.abs(power.Power / 1000).toFixed(1)} W`
    : "";
  $("gallons").textContent = water ? water.gallons.toFixed(1) : "—";
  $("water-bar").style.setProperty("--pct", `${water?.percent ?? 0}%`);
  $("water-bar").classList.toggle("low", !!water?.low);
  $("water-note").textContent = water
    ? `${water.percent}% full · ${water.distance.toFixed(1)} cm to surface`
    : "Unavailable";
  $("water-low").hidden = !water?.low;
}

function showLight(value) {
  $("light-value").textContent = value == null ? "—" : Math.round(value);
  if (value != null) range.value = value;
  range.style.setProperty("--pct", `${range.value}%`);
}

function showPump() {
  const on = !!pump?.on;
  const left = pump?.seconds_left ?? 0;
  $("pump-state").textContent = pump ? (on ? "On" : "Off") : "—";
  $("pump-value").classList.toggle("on", on);
  $("countdown").textContent = on && left > 0
    ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`
    : "";
  $("pump-toggle").value = on ? "off" : "on";
  $("pump-toggle").textContent = on ? "Turn off" : "Turn on";
}

function showSchedule(schedule) {
  const on = schedule.enabled;
  $("schedule-state").textContent = on ? schedule.label : "Off";
  $("schedule-value").classList.toggle("on", on);
  $("schedule-until").textContent = on && schedule.until
    ? `until ${shortDate(schedule.until)}`
    : "";
  $("schedule-detail").textContent = on
    ? `Light ${schedule.light} · Pump ${schedule.pump} · Next watering ${schedule.next_watering}`
    : `Paused. ${schedule.label} would run: light ${schedule.light}, pump ${schedule.pump}`;
  $("schedule-toggle").value = on ? "off" : "on";
  $("schedule-toggle").textContent = on ? "Turn off" : "Turn on";
  for (const button of document.querySelectorAll("[data-preset]")) {
    button.setAttribute("aria-pressed", on && button.value === schedule.preset);
  }
}

const shortDate = (iso) =>
  new Date(`${iso}T00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function showCycle(cycle) {
  const started = !!cycle.started;
  $("cycle-day").textContent = started ? `Day ${cycle.day}` : "Not started";
  $("cycle-stage").textContent = started ? cycle.stage : "";
  $("cycle-detail").textContent = started
    ? `Started ${shortDate(cycle.started)}${cycle.next ? ` · Next: ${cycle.next.toLowerCase()}` : ""}`
    : "Start a cycle to get thinning, root, harvest and plant-food reminders.";
  if (started && document.activeElement !== $("cycle-started")) $("cycle-started").value = cycle.started;
  $("reminders").replaceChildren(...cycle.due.map(({ key, label }) => {
    const form = Object.assign(document.createElement("form"), { method: "post", action: "/cycle" });
    form.className = "reminder";
    form.innerHTML = `<span></span><input type="hidden" name="action" value="done">
      <button name="key">Done</button>`;
    form.querySelector("span").textContent = label;
    form.querySelector("button").value = key;
    return form;
  }));
}

setInterval(() => {
  if (pump?.on && pump.seconds_left > 0) {
    pump.seconds_left -= 1;
    if (pump.seconds_left === 0) pump.on = false; // the next snapshot confirms
    showPump();
  }
}, 1000);

range.addEventListener("pointerdown", () => (dragging = true));
addEventListener("pointerup", () => (dragging = false));
range.addEventListener("input", () => {
  $("light-value").textContent = range.value;
  range.style.setProperty("--pct", `${range.value}%`);
});
range.addEventListener("change", () => {
  dragging = false;
  range.form.requestSubmit();
});

document.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  // Reminders sit above the sections; their errors show in the cycle panel.
  const error = (form.closest("section") ?? document.querySelector("section.cycle")).querySelector(".error");
  error.textContent = "";
  try {
    const response = await fetch(form.getAttribute("action"), { // form.action is shadowed by controls named "action"
      method: "POST",
      body: new FormData(form, event.submitter),
    });
    if (!response.ok) error.textContent = (await response.json()).error;
  } catch {
    error.textContent = "The garden didn't respond";
  }
});
