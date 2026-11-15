// Added to the page before its own scripts, in the browser tests: a phone's rules for playing sound, and a count of
// what was really heard.
//
// Headless Chromium plays sound whenever asked, but phones don't. So here, as on iOS Safari, an audio element may
// start only while the learner is tapping (a real, trusted tap) or later if a tap has already started that element.
// window.phone.revoke() takes that permission back, as phones do when the microphone opens or closes, and
// window.phone.interrupt() pauses the voice the way a phone does by itself.
(() => {
  let tapping = false;
  for (const type of ['pointerup', 'touchend', 'keydown']) {
    addEventListener(type, e => {
      if (!e.isTrusted) return;
      tapping = true;
      setTimeout(() => (tapping = false), 0);   // over once this tap's handlers have run
    }, {capture: true});
  }

  let allowed = new WeakSet();
  const watched = new WeakSet();
  const phone = window.phone = {
    sentences: 0,      // sentences of the tutor's voice played to their end
    refused: 0,        // play() calls the phone refused
    current: null,     // the element playing now
    log: [],           // what happened, for a failing test's message
    revoke: () => (allowed = new WeakSet()),
    interrupt: () => phone.current && !phone.current.paused && phone.current.pause(),
  };

  const play = HTMLMediaElement.prototype.play;
  const name = audio => audio.src.slice(-5);
  HTMLMediaElement.prototype.play = function () {
    if (tapping) allowed.add(this);
    if (!allowed.has(this)) {
      phone.refused++;
      phone.log.push(`refused ${name(this)}`);
      return Promise.reject(new DOMException('The phone wants a tap first.', 'NotAllowedError'));
    }
    phone.log.push(`play ${name(this)}${tapping ? ' (tap)' : ''}`);
    if (!watched.has(this)) {
      watched.add(this);
      // Noted when it starts: by the time 'ended' reaches this listener, the page has already loaded the next one.
      let playing = {name: '', seconds: 0};
      this.addEventListener('playing', () => (playing = {name: name(this), seconds: this.duration}));
      this.addEventListener('ended', () => {
        phone.log.push(`ended ${playing.name} ${playing.seconds.toFixed(2)} s`);
        if (playing.seconds > 0.2) phone.sentences++;   // the page's moment of silence is 0.05 s
      });
    }
    phone.current = this;
    return play.call(this);
  };
})();
