# -*- coding: utf-8 -*-
"""对一次练习会话做离线批改。

Part A      ：Levenshtein WER
Part B SecA ：Jaccard 与正确选项文本比对
Part B SecB ：Jaccard 与标准答案比对
Part C SecA ：关键短语覆盖
Part C SecB ：Jaccard 与标准提问比对
"""

from .asr import recognize_audio_file
from .scoring import jaccard_similarity, keyword_coverage, levenshtein_wer


def evaluate_recordings(session, pkg, vosk_model, existing_eval=None, selection=None):
    """返回批改结果字典。

    existing_eval 用于“只重新批改某一部分”时保留其它部分的旧结果；
    selection 为 None 时全量批改，否则形如 {"partA": True, "partC_secB": True}。
    """
    eval_result = dict(existing_eval) if existing_eval else {}
    _all = (selection is None)

    # Part A
    if _all or selection.get('partA'):
        if session.partA_recording:
            hyp = recognize_audio_file(session.partA_recording, vosk_model)
            wer, acc = levenshtein_wer(pkg.partA_hidden_text, hyp)
            eval_result['partA'] = {'recognized': hyp, 'wer': wer, 'accuracy': acc}
        else:
            eval_result['partA'] = {'recognized': '', 'wer': 1.0, 'accuracy': 0.0}

    # Part B SecA
    old_a = eval_result.get('partB_secA', [])
    new_a = []
    rec_idx = 0
    for seg_idx, seg in enumerate(pkg.partB_secA):
        for q_idx, q in enumerate(seg.get("questions", [])[:2]):
            if _all or (selection and selection.get('partB_secA')):
                if rec_idx < len(session.partB_secA_recordings):
                    rec = session.partB_secA_recordings[rec_idx]
                    hyp = recognize_audio_file(rec, vosk_model) if rec else ""
                    correct_text = q.get("correct_option_text", "")
                    sim = jaccard_similarity(correct_text, hyp) if hyp else 0.0
                    new_a.append({"seg": seg_idx + 1, "q": q_idx + 1,
                                  "recognized": hyp, "correct": correct_text,
                                  "similarity": sim})
                else:
                    new_a.append({"seg": seg_idx + 1, "q": q_idx + 1,
                                  "recognized": "", "correct": "",
                                  "similarity": 0.0})
            else:
                new_a.append(old_a[rec_idx] if rec_idx < len(old_a) else
                             {"seg": seg_idx + 1, "q": q_idx + 1, "similarity": 0.0})
            rec_idx += 1
    eval_result['partB_secA'] = new_a

    # Part B SecB
    old_b = eval_result.get('partB_secB', [])
    new_b = []
    for i, q in enumerate(pkg.partB_secB.get("questions", [])):
        if _all or (selection and selection.get('partB_secB')):
            if i < len(session.partB_secB_recordings) and session.partB_secB_recordings[i]:
                rec = session.partB_secB_recordings[i]
                hyp = recognize_audio_file(rec, vosk_model)
                ref = q.get("hidden_answer", "")
                sim = jaccard_similarity(ref, hyp) if hyp else 0.0
                new_b.append({"q": i + 1, "recognized": hyp,
                              "correct": ref, "similarity": sim})
            else:
                new_b.append({"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
        else:
            new_b.append(old_b[i] if i < len(old_b) else
                         {"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
    eval_result['partB_secB'] = new_b

    # Part C SecA
    if _all or selection.get('partC_secA'):
        if session.partC_secA_recording:
            hyp = recognize_audio_file(session.partC_secA_recording, vosk_model)
            found, total, _ = keyword_coverage(hyp, pkg.partC_secA.get("hidden_answer_points", ""))
            eval_result['partC_secA'] = {'recognized': hyp,
                                          'coverage': f"{found}/{total}",
                                          'found': found, 'total': total}
        else:
            eval_result['partC_secA'] = {'recognized': '', 'coverage': '0/0',
                                          'found': 0, 'total': 0}

    # Part C SecB
    old_c = eval_result.get('partC_secB', [])
    new_c = []
    for i, q in enumerate(pkg.partC_secB.get("questions", [])):
        if _all or (selection and selection.get('partC_secB')):
            if i < len(session.partC_secB_recordings) and session.partC_secB_recordings[i]:
                rec = session.partC_secB_recordings[i]
                hyp = recognize_audio_file(rec, vosk_model)
                ref = q.get("hidden_question", "")
                sim = jaccard_similarity(ref, hyp) if hyp else 0.0
                new_c.append({"q": i + 1, "recognized": hyp,
                              "correct": ref, "similarity": sim})
            else:
                new_c.append({"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
        else:
            new_c.append(old_c[i] if i < len(old_c) else
                         {"q": i + 1, "recognized": "", "correct": "", "similarity": 0.0})
    eval_result['partC_secB'] = new_c

    return eval_result
