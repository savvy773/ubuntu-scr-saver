export {};
    const daysEn = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
    const daysKo = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];

    const hoursEl = document.getElementById('hours')!;
    const minutesEl = document.getElementById('minutes')!;
    const secondsEl = document.getElementById('seconds')!;
    const ampmEl = document.getElementById('ampm')!;
    const dateTextEl = document.getElementById('dateText')!;
    const dayBadgeEl = document.getElementById('dayBadge')!;
    const progressBarEl = document.getElementById('progressBar')!;

    function setText(element: HTMLElement, text: string) {
      if (element.textContent !== text) element.textContent = text;
    }

    function updateTime() {
      const now = new Date();
      let h = now.getHours();
      const m = String(now.getMinutes()).padStart(2, '0');
      const s = now.getSeconds();
      const ms = now.getMilliseconds();

      const isPm = h >= 12;
      const ampm = isPm ? 'PM' : 'AM';
      const displayHours = String(h % 12 || 12).padStart(2, '0');

      setText(hoursEl, displayHours);
      setText(minutesEl, m);
      setText(secondsEl, String(s).padStart(2, '0'));
      setText(ampmEl, ampm);

      // 날짜
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const date = String(now.getDate()).padStart(2, '0');
      setText(dateTextEl, `${year}. ${month}. ${date}`);
      setText(dayBadgeEl, `${daysKo[now.getDay()]} / ${daysEn[now.getDay()]}`);

      // 프로그레스 바 (초 단위)
      const progressPercent = ((s + ms / 1000) / 60) * 100;
      progressBarEl.style.width = `${progressPercent}%`;
    }

    setInterval(updateTime, 1000);
    updateTime();

    // 시작 직후의 키 입력을 무시하고, 키보드 입력으로만 종료합니다.
    let ready = false;

    setTimeout(() => {
      ready = true;
    }, 800);

    function exitScreensaver() {
      if (!ready || document.querySelector('dialog[open]')) return;
      window.close();
    }

    window.addEventListener('keydown', exitScreensaver);
