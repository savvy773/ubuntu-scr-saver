export {};
type Target = 'ram' | 'ssd' | 'hdd';
type Info = { token: string; memoryCacheBytes: number; ssdPaths: string[]; hddMounted: boolean };
type Preview = { previewId: string; target: Target; fileCount: number; bytes: number; paths: string[]; days: number };
type Result = { target: Target; fileCount: number; bytes: number; skipped?: number; beforeBytes?: number; afterBytes?: number };
const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const dialog = element<HTMLDialogElement>('maintenanceDialog');
const close = element<HTMLButtonElement>('maintenanceClose');
const description = element('maintenanceDescription');
const pathField = element('maintenancePathField');
const path = element<HTMLInputElement>('maintenancePath');
const ageField = element('maintenanceAgeField');
const age = element<HTMLSelectElement>('maintenanceAge');
const previewButton = element<HTMLButtonElement>('maintenancePreview');
const summary = element('maintenanceSummary');
const estimate = element('maintenanceEstimate');
const paths = element('maintenancePaths');
const confirm = element<HTMLInputElement>('maintenanceConfirm');
const execute = element<HTMLButtonElement>('maintenanceExecute');
const status = element('maintenanceStatus');
const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-cache-target]'));
let target: Target = 'ssd';
let info: Info | undefined;
let preview: Preview | undefined;
let busy = false;
const formatBytes = (bytes: number) => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GiB`
  : bytes >= 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} MiB` : `${(bytes / 1024).toFixed(1)} KiB`;
try { path.value = localStorage.getItem('screensaver-hdd-cache-path') ?? ''; } catch { /* Optional preference. */ }

function invalidate() {
  preview = undefined;
  confirm.checked = false;
  summary.hidden = true;
  execute.disabled = true;
  status.textContent = '';
}
function setBusy(value: boolean) {
  busy = value;
  close.disabled = value;
  previewButton.disabled = value || !info;
  tabs.forEach(tab => tab.disabled = value);
  path.disabled = age.disabled = confirm.disabled = value;
  execute.disabled = value || !preview || !confirm.checked || (target !== 'ram' && preview.fileCount === 0);
}
function select(next: Target) {
  target = next;
  invalidate();
  tabs.forEach(tab => tab.setAttribute('aria-pressed', String(tab.dataset.cacheTarget === target)));
  pathField.hidden = target !== 'hdd';
  ageField.hidden = target === 'ram';
  updateDescription();
}
function updateDescription() {
  if (target === 'ram') {
    description.textContent = `Linux 파일 읽기·메타데이터 캐시를 수동으로 비웁니다. 현재 캐시 약 ${formatBytes(info?.memoryCacheBytes ?? 0)}. 관리자 권한이 필요하며, 정리 후 파일을 다시 읽을 때 일시적으로 느려질 수 있습니다.`;
  } else if (target === 'ssd') {
    description.textContent = '사용자 폴더의 썸네일·폰트·셰이더·Chrome 캐시 파일을 정리합니다. 정리 범위와 파일 수를 먼저 확인하세요. 캐시는 다음 사용 때 다시 생성될 수 있습니다.';
  } else {
    description.textContent = info?.hddMounted
      ? 'HDD 안의 썸네일·폰트·Mesa 셰이더·Chrome 캐시 폴더만 지정할 수 있습니다. uv·pnpm 등 패키지 캐시, 의존성, 임의의 cache/tmp 폴더는 제외됩니다.'
      : 'HDD가 연결되어 있지 않습니다. 연결한 뒤 캐시 폴더를 지정하세요.';
  }
}
async function post<T>(route: string, data: object): Promise<T> {
  const response = await fetch(`/api/maintenance/${route}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: info?.token, ...data }), signal: AbortSignal.timeout(35000)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error ?? '요청을 처리하지 못했습니다');
  return result as T;
}
element<HTMLButtonElement>('maintenanceOpen').addEventListener('click', async () => {
  dialog.showModal();
  invalidate();
  info = undefined;
  setBusy(true);
  status.textContent = '캐시 정보를 읽는 중…';
  try {
    const response = await fetch('/api/maintenance', { cache: 'no-store', signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error('캐시 서비스에 연결할 수 없습니다');
    info = await response.json() as Info;
    select(target);
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : '연결 오류';
  } finally { setBusy(false); }
});
close.addEventListener('click', () => dialog.close());
dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
tabs.forEach(tab => tab.addEventListener('click', () => select(tab.dataset.cacheTarget as Target)));
age.addEventListener('change', invalidate);
path.addEventListener('input', invalidate);
confirm.addEventListener('change', () => setBusy(false));
previewButton.addEventListener('click', async () => {
  invalidate();
  setBusy(true);
  status.textContent = '정리 대상 확인 중…';
  try {
    preview = await post<Preview>('preview', { target, path: path.value.trim(), days: Number(age.value) });
    if (target === 'hdd') {
      try { localStorage.setItem('screensaver-hdd-cache-path', path.value.trim()); } catch { /* Optional preference. */ }
    }
    paths.replaceChildren(...preview.paths.map(value => { const item = document.createElement('li'); item.textContent = value; return item; }));
    estimate.textContent = target === 'ram' ? `읽기 캐시 약 ${formatBytes(preview.bytes)}`
      : `${preview.fileCount.toLocaleString()}개 파일 · 예상 ${formatBytes(preview.bytes)}`;
    summary.hidden = false;
    status.textContent = target !== 'ram' && preview.fileCount === 0 ? '현재 조건에 맞는 캐시 파일이 없습니다.' : '표시된 대상을 확인한 뒤 정리할 수 있습니다.';
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : '확인 오류';
  } finally { setBusy(false); }
});
execute.addEventListener('click', async () => {
  if (!preview || !confirm.checked || busy) return;
  setBusy(true);
  status.textContent = '캐시 정리 중…';
  try {
    const result = await post<Result>('execute', { previewId: preview.previewId, confirmed: true });
    window.dispatchEvent(new Event('resources:refresh'));
    if (result.target === 'ram' && result.afterBytes !== undefined) {
      if (info) info.memoryCacheBytes = result.afterBytes;
      estimate.textContent = `현재 읽기 캐시 ${formatBytes(result.afterBytes)}`;
      updateDescription();
    }
    status.textContent = result.target === 'ram' ? `읽기 캐시 정리 완료 · 전 ${formatBytes(result.beforeBytes ?? 0)} → 후 ${formatBytes(result.afterBytes ?? 0)} · 감소 ${formatBytes(result.bytes)}. 회수 가능한 캐시는 RAM 사용률에서 제외되어 사용률 변화가 작을 수 있습니다.`
      : `${result.fileCount.toLocaleString()}개 캐시 파일 정리 · ${formatBytes(result.bytes)}${result.skipped ? ` · 변경된 파일 등 ${result.skipped}개 제외` : ''}`;
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : '정리 오류';
  } finally {
    preview = undefined;
    confirm.checked = false;
    setBusy(false);
  }
});
