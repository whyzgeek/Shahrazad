"""The text handling between the brain and the voice: sentences, vowel merging, spelling fixes and cleaning."""
import app

REPLIES = [
    "نقول: أمس ذهبتُ إلى السوق مع أختي واشتريتُ خبزاً طازجاً. هل تحب التسوق في الأسواق الشعبية أم تفضل المراكز التجارية؟",
    "نعم. السفر ممتع جداً، ومصر والمغرب بلدان رائعان. أي بلد أعجبك أكثر؟",
    "حسناً، إليك بعض العناوين من قناة الجزيرة. هل تريد الحديث عن الاقتصاد أم عن الرياضة؟ اختر واحداً.",
]


def test_split_sentences_merges_short_fragments():
    assert app.split_sentences("نعم. السفر ممتع جداً في الصيف.") == ["نعم، السفر ممتع جداً في الصيف."]
    assert app.split_sentences("هذا جميل جداً. شكراً.") == ["هذا جميل جداً. شكراً،"]
    assert app.split_sentences("") == []


def test_complete_sentences_agree_with_the_final_split():
    """Sentences voiced while the reply is still arriving must be the ones the final split finds. The one exception:
    a short closing fragment joins the last sentence, and respond() then voices just the fragment."""
    for reply in REPLIES:
        final = app.split_sentences(reply)
        for cut in range(1, len(reply) + 1):
            done = app.complete_sentences(reply[:cut])
            assert len(done) <= len(final)
            for i, d in enumerate(done):
                assert final[i] == d or (i == len(final) - 1 and final[i].startswith(d)), (reply[:cut], d)


def test_split_long_keeps_every_word_under_the_limit():
    words = ["كلمة"] * 47
    text = "، ".join(" ".join(words[i:i + 9]) for i in range(0, 47, 9))
    parts = app.split_long(text, limit=20)
    assert all(len(p.split()) <= 20 for p in parts)
    assert " ".join(parts).replace("،", "").split() == text.replace("،", "").split()


def test_merge_vowels_keeps_the_tutors_words():
    plain = "ذهب الطالب إلى المدرسة"
    assert app.merge_vowels(plain, "ذَهَبَ الطَّالِبُ إِلَى الْمَدْرَسَةِ") == "ذَهَبَ الطَّالِبُ إِلَى الْمَدْرَسَةِ"
    # A different word is not taken: the original stays, without marks.
    assert app.merge_vowels(plain, "ذَهَبَ الْوَلَدُ إِلَى الْمَدْرَسَةِ") == "ذَهَبَ الطالب إِلَى الْمَدْرَسَةِ"
    # A small spelling fix is taken.
    assert app.merge_vowels("بط عرج", "بَطٌّ أَعْرَجُ") == "بَطٌّ أَعْرَجُ"


def test_apply_spelling_carries_the_fix_into_the_shown_text():
    assert app.apply_spelling("وصفه بأنه بط عرج.", "وَصَفَهُ بِأَنَّهُ بَطٌّ أَعْرَجُ.") == "وصفه بأنه بط أعرج."
    assert app.apply_spelling("ذهب الطالب.", "ذَهَبَ الطَّالِبُ.") == "ذهب الطالب."


def test_fix_initial_sukun():
    assert app.fix_initial_sukun("تْرَامْب قَالَ") == "تِرَامْب قَالَ"


def test_bare_words():
    assert app.bare_words("ذَهَبَ الطالب إِلَى و") == [1]


def test_speakable_and_clean_text():
    assert app.speakable("ذهب الطالب إلى المدرسة.")
    assert not app.speakable("This is English.")
    assert app.clean_text("«مرحباً»... قالَ **المعلم**") == "مرحبا، قال المعلم"
