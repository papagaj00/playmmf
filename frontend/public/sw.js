self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "PlayMMF";
  const options = {
    body: data.body || "Máte novou aktualitu.",
    icon: "/playmmf-logo.svg",
    badge: "/playmmf-logo.svg",
    data: { marketId: data.market_id },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const existing = windows.find((window) => "focus" in window);
      if (existing) return existing.focus();
      return clients.openWindow(self.registration.scope);
    })
  );
});
