(function () {
  "use strict";

  var root = document.documentElement;
  var themeButton = document.getElementById("themeToggle");
  var copyButton = document.getElementById("copyCommand");
  var copyStatus = document.getElementById("copyStatus");
  var installCommand = document.getElementById("installCommand");

  function syncThemeLabel() {
    if (!themeButton) return;
    themeButton.setAttribute(
      "aria-label",
      root.dataset.theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
    );
  }

  if (themeButton) {
    themeButton.addEventListener("click", function () {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      localStorage.theme = root.dataset.theme;
      syncThemeLabel();
    });
  }

  if (copyButton && copyStatus && installCommand) {
    copyButton.addEventListener("click", async function () {
      try {
        await navigator.clipboard.writeText(installCommand.textContent);
        copyButton.textContent = "Copied";
        copyStatus.textContent = "Install commands copied to the clipboard.";
      } catch (_error) {
        copyButton.textContent = "Select";
        copyStatus.textContent = "Clipboard access is unavailable. Select the commands manually.";
      }
    });
  }

  syncThemeLabel();
})();
