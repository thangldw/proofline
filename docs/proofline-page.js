(function () {
  "use strict";

  var demoCommand = "proofline demo stale-decision";
  var copyButtons = [
    document.querySelector("#copy-demo"),
    document.querySelector("#copy-demo-primary"),
  ];
  var copyStatus = document.querySelector("#copy-status");

  async function copyQuickstart() {
    try {
      await navigator.clipboard.writeText(demoCommand);
      copyStatus.textContent = "Demo command copied. Paste it into your terminal.";
    } catch (_error) {
      copyStatus.textContent = demoCommand;
    }
  }

  copyButtons.forEach(function (button) {
    button.addEventListener("click", copyQuickstart);
  });
})();
