(function () {
  "use strict";

  var installCommands = "pip install proofline-0.14.16-py3-none-any.whl\nproofline launch";
  var copyButtons = [
    document.querySelector("#copy-demo"),
    document.querySelector("#copy-demo-primary"),
  ];
  var copyStatus = document.querySelector("#copy-status");

  async function copyQuickstart() {
    try {
      await navigator.clipboard.writeText(installCommands);
      copyStatus.textContent = "Quickstart copied. Download the wheel, then paste into your terminal.";
    } catch (_error) {
      copyStatus.textContent = installCommands;
    }
  }

  copyButtons.forEach(function (button) {
    button.addEventListener("click", copyQuickstart);
  });
})();
