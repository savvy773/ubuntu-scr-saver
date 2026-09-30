export {};
type Resource = { percent: number; used: number; total: number; remaining?: number; available?: boolean };
type ResourceName = 'cpu' | 'ram' | 'disk' | 'hdd';
type Resources = Record<ResourceName, Resource> & { frontendVersion: string };
const names: ResourceName[] = ['cpu', 'ram', 'disk', 'hdd'];
const thresholds: Record<ResourceName, [number, number]> = {
  cpu: [60, 85], ram: [75, 90], disk: [80, 90], hdd: [80, 90]
};

(() => {
  const statusEl = document.getElementById('resourceStatus')!;
  const liveEl = document.getElementById('liveLabel')!;
  let frontendVersion: string | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let updating = false;
  let refreshRequested = false;
  const gib = (bytes: number) => (bytes / (1024 ** 3)).toFixed(1);
  function setText(element: HTMLElement, value: string) {
    if (element.textContent !== value) element.textContent = value;
  }

  async function updateResources() {
    if (updating) { refreshRequested = true; return; }
    clearTimeout(timer);
    updating = true;
    try {
      const response = await fetch('/api/resources', {
        cache: 'no-store', signal: AbortSignal.timeout(2500)
      });
      if (!response.ok) throw new Error('Resource readings unavailable');
      const data: Resources = await response.json();
      if (frontendVersion && data.frontendVersion !== frontendVersion) {
        window.location.reload();
        return;
      }
      frontendVersion = data.frontendVersion;
      for (const name of names) {
        const resource = data[name];
        const valueEl = document.getElementById(`${name}Value`)!;
        const card = valueEl.closest<HTMLElement>('.resource-card')!;
        const levelEl = document.getElementById(`${name}Level`)!;
        if (resource.available === false) {
          card.dataset.level = 'offline';
          card.style.setProperty('--usage', '0');
          setText(levelEl, 'OFFLINE');
          setText(valueEl, '—');
          const detail = document.getElementById(`${name}Detail`)!;
          detail.dataset.unavailable = 'true';
          setText(document.getElementById(`${name}Used`)!, '—');
          setText(document.getElementById(`${name}Remaining`)!, '—');
          continue;
        }
        const [warning, high] = thresholds[name];
        const level = resource.percent >= high ? 'high' : resource.percent >= warning ? 'warning' : 'normal';
        if (card.dataset.level !== level) card.dataset.level = level;
        const usage = String(Math.max(0, Math.min(100, resource.percent)) / 100);
        if (card.style.getPropertyValue('--usage') !== usage) card.style.setProperty('--usage', usage);
        setText(levelEl, { normal: 'NORMAL', warning: 'WATCH', high: 'HIGH' }[level]);
        card.title = `주의 ${warning}% · 높음 ${high}%`;
        setText(valueEl, `${resource.percent.toFixed(1)}%`);
        if (name !== 'cpu') {
          const detail = document.getElementById(`${name}Detail`)!;
          delete detail.dataset.unavailable;
          setText(document.getElementById(`${name}Used`)!, `${gib(resource.used)} GiB`);
          setText(document.getElementById(`${name}Remaining`)!,
            resource.remaining === undefined ? '—' : `${gib(resource.remaining)} GiB`);
          detail.title = `전체 ${gib(resource.total)} GiB`;
        }
      }
      setText(statusEl, '');
      setText(liveEl, 'LIVE');
      liveEl.classList.add('live');
    } catch (_) {
      // Keep the last valid readings and bar positions during transient failures.
      setText(liveEl, 'RECONNECTING');
      liveEl.classList.remove('live');
      setText(statusEl, '최근 수치를 표시 중 · 연결 재시도');
    } finally {
      updating = false;
      timer = setTimeout(updateResources, refreshRequested ? 0 : 3000);
      refreshRequested = false;
    }
  }
  window.addEventListener('resources:refresh', updateResources);
  updateResources();
})();
