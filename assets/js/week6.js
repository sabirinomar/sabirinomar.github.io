document.addEventListener("DOMContentLoaded", () => {
  const toggles = document.querySelectorAll("[data-toggle]");

  toggles.forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("data-toggle");
      const target = document.getElementById(targetId);

      if (!target) {
        return;
      }

      const isHidden = target.hasAttribute("hidden");
      target.toggleAttribute("hidden", !isHidden);
      button.textContent = isHidden ? "Hide more context" : "Show more context";
    });
  });
});
