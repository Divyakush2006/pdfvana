// Light theme by default; dark only when the visitor has switched to it.
try {
  if (localStorage.getItem("theme") === "dark") document.documentElement.classList.add("dark");
} catch (e) {}
