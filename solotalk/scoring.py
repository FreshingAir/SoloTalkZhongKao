# -*- coding: utf-8 -*-
"""评分算法：文本相似度工具 + 按分制换算各项得分。

相似度工具：
    levenshtein_wer    词级编辑距离 / WER（Part A 模仿朗读）
    jaccard_similarity 词集合 Jaccard（Part B/C 口头回答）
    keyword_coverage   关键短语覆盖率（Part C 信息转述）
"""

from .config import get_scheme


def levenshtein_wer(ref, hyp):
    """返回 (wer, accuracy)，两者互补；ref 为空时按 hyp 是否为空判定。"""
    ref_words = ref.lower().split()
    hyp_words = hyp.lower().split()
    n = len(ref_words)
    if n == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0, 1.0 if len(hyp_words) == 0 else 0.0
    dp = [[0] * (len(hyp_words) + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, len(hyp_words) + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    wer = dp[n][len(hyp_words)] / n
    return wer, 1.0 - wer


def jaccard_similarity(text1, text2):
    set1 = set(text1.lower().split())
    set2 = set(text2.lower().split())
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


def keyword_coverage(text, keywords_str):
    """返回 (命中数, 关键短语总数, 命中的短语列表)。"""
    keywords = [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]
    if not keywords:
        return 0, 0, []
    text_lower = text.lower()
    found = [kw for kw in keywords if kw in text_lower]
    return len(found), len(keywords), found


def compute_scores(eval_result, scheme_key):
    """根据批改结果和分制计算各项得分。"""
    scheme = get_scheme(scheme_key)
    scores = {
        "scheme": str(scheme_key),
        "scheme_name": scheme["name"],
        "total_max": scheme["total"],
        "detail": {},
    }
    total = 0.0

    # Part A：accuracy × 满分
    pa = eval_result.get("partA", {})
    pa_max = scheme["partA"]["per"] * scheme["partA"]["count"]
    pa_score = round(max(0.0, min(1.0, pa.get("accuracy", 0.0))) * pa_max, 2)
    scores["detail"]["partA"] = {"score": pa_score, "max": pa_max}
    total += pa_score

    # Part B SecA：选择题，相似度 ≥ 0.5 得满分
    secA_list = eval_result.get("partB_secA", [])
    secA_per = scheme["partB_secA"]["per"]
    secA_max = secA_per * scheme["partB_secA"]["count"]
    secA_score = 0.0
    for item in secA_list:
        if item.get("similarity", 0.0) >= 0.5:
            secA_score += secA_per
    secA_score = round(min(secA_score, secA_max), 2)
    scores["detail"]["partB_secA"] = {"score": secA_score, "max": secA_max,
                                      "items": len(secA_list)}
    total += secA_score

    # Part B SecB：similarity 折算
    secB_list = eval_result.get("partB_secB", [])
    secB_per = scheme["partB_secB"]["per"]
    secB_max = secB_per * scheme["partB_secB"]["count"]
    secB_score = 0.0
    for item in secB_list:
        sim = max(0.0, min(1.0, item.get("similarity", 0.0)))
        secB_score += sim * secB_per
    secB_score = round(min(secB_score, secB_max), 2)
    scores["detail"]["partB_secB"] = {"score": secB_score, "max": secB_max,
                                      "items": len(secB_list)}
    total += secB_score

    # Part C SecA：要点覆盖率 × 满分
    pcA = eval_result.get("partC_secA", {})
    pcA_max = scheme["partC_secA"]["per"] * scheme["partC_secA"]["count"]
    cov_total = pcA.get("total", 0)
    cov_found = pcA.get("found", 0)
    cov_ratio = (cov_found / cov_total) if cov_total > 0 else 0.0
    pcA_score = round(cov_ratio * pcA_max, 2)
    scores["detail"]["partC_secA"] = {"score": pcA_score, "max": pcA_max,
                                      "coverage": f"{cov_found}/{cov_total}"}
    total += pcA_score

    # Part C SecB：similarity 折算
    pcB_list = eval_result.get("partC_secB", [])
    pcB_per = scheme["partC_secB"]["per"]
    pcB_max = pcB_per * scheme["partC_secB"]["count"]
    pcB_score = 0.0
    for item in pcB_list:
        sim = max(0.0, min(1.0, item.get("similarity", 0.0)))
        pcB_score += sim * pcB_per
    pcB_score = round(min(pcB_score, pcB_max), 2)
    scores["detail"]["partC_secB"] = {"score": pcB_score, "max": pcB_max,
                                      "items": len(pcB_list)}
    total += pcB_score

    scores["total"] = round(total, 2)
    return scores
