// Starts the page: sets up each part, then connects to the tutor and routes each message it sends to the part that
// shows it. The messages are listed in one table, so it's easy to see what the server can say.
import {connect} from './connection.js';
import * as conversation from './conversation.js';
import {addCorrection, setupCorrections} from './corrections.js';
import {hideGloss, setupGloss} from './gloss.js';
import {setupLayout} from './layout.js';
import {onOptionChange, setupOptions} from './options.js';
import {checkHealth, setupPanels} from './panels.js';
import {play, setupPlayer, stopAudio} from './player.js';
import {renderSessions, setupSessions} from './sessions.js';
import {sendText, setBusy, setConnected, setupTalk, updateState} from './talk.js';
import {DEBUG, setStatus} from './util.js';

const sourceKind = kind => kind === 'video' ? 'Video' : 'Article';

const events = {
  // While the learner speaks, and when they've finished.
  partial: m => conversation.heard(m.text),
  final: m => {
    conversation.heardFinal(m.text);
    if (!m.text) setBusy(false);
  },
  // The tutor's reply: as it's written, as its sentences get their vowels, and once it's saved.
  assistant: m => {
    conversation.tutorWrites(m.text);
    setStatus('');
  },
  tashkeel: m => conversation.tutorVowels(m.display ?? m.text, m.covered ?? 0),
  turn: m => conversation.turnSaved(m.id, m.n),
  timing: m => {
    setBusy(false);
    if (DEBUG) conversation.showTiming(m.end_of_speech_to_first_audio_s);
  },
  replay_done: () => conversation.replayFinished(),
  text_only: () => setStatus('Shown as text only: the Arabic voice can’t read that language.'),
  // What the conversation is about.
  subject: m => {
    const section = m.sections > 1 ? ` (${m.section}/${m.sections})` : '';
    conversation.sourceCard(sourceKind(m.kind), m.title + section, m.url);
    setStatus('');
  },
  items: m => {
    m.items.forEach((item, i) => conversation.sourceCard('Option ' + (i + 1), item.title, item.url));
    setStatus('');
  },
  // Corrections found after a turn.
  errors: m => m.errors.forEach(addCorrection),
  // Conversations: the sidebar list, and a whole conversation when one is opened.
  sessions: m => renderSessions(m),
  session: m => {
    stopAudio();
    hideGloss();
    setBusy(false);
    setStatus('');
    conversation.loadConversation(m);
  },
  status: m => setStatus(m.text),
  error: m => {
    setStatus(m.text);
    setBusy(false);
  },
};

setupOptions();
setupLayout(hideGloss);
setupPlayer();
setupCorrections();
setupGloss();
setupSessions();
setupPanels();
setupTalk();
conversation.setupConversation({onStart: sendText});
onOptionChange(name => {
  if (name === 'marks') conversation.rerender();
});

connect({
  onOpen: () => {
    setConnected(true);
    checkHealth();
  },
  onClose: () => {
    setConnected(false);
    checkHealth();
  },
  onEvent: m => {
    events[m.type]?.(m);
    updateState();
  },
  onAudio: play,
});
