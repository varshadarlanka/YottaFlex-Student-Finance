"""
backend/anomaly/evaluator.py
==============================
Evaluation of detection results against ground truth.

Computes:
- True positives (TP): detected issues that match injected anomalies
- False positives (FP): detected issues with no ground-truth match
- False negatives (FN): injected anomalies that were not detected
- Precision = TP / (TP + FP)
- Recall    = TP / (TP + FN)
- F1 score  = 2 * Precision * Recall / (Precision + Recall)

Ground truth is only used AFTER detection is complete.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from backend.anomaly.detector import DetectedIssue
from backend.anomaly.injector import GroundTruthRecord

logger = logging.getLogger(__name__)

ISSUE_TYPE_MAP = {
    "PAYMENT_ALLOC_EXCEEDS_PAYMENT": "PAYMENT_ALLOC_EXCEEDS_PAYMENT",
    "SCHOLARSHIP_EXCEEDS_FEES": "SCHOLARSHIP_EXCEEDS_FEES",
    "DUPLICATE_INVOICE": "DUPLICATE_INVOICE",
    "REFUND_EXCEEDS_NET_PAID": "REFUND_EXCEEDS_NET_PAID",
    "BALANCE_DISAGREES_LEDGER": "BALANCE_DISAGREES_LEDGER",
}


@dataclass
class EvaluationResult:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    detected_count: int
    ground_truth_count: int
    tp_issues: List[str] = field(default_factory=list)   # issue_ids matched
    fp_issues: List[str] = field(default_factory=list)   # detected but no GT
    fn_issues: List[str] = field(default_factory=list)   # GT but not detected
    per_type: Dict[str, Dict] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


class AnomalyEvaluator:
    """
    Compare detection results with ground truth after detection.
    """

    def evaluate(
        self,
        detected: List[DetectedIssue],
        ground_truth: List[GroundTruthRecord],
    ) -> EvaluationResult:
        """
        Match detected issues to ground-truth records by issue_type.

        Detections match labels by issue type and primary entity ID. Each
        detection and ground-truth record can participate in at most one match.
        """
        gt_matched: Set[str] = set()       # GT issue_ids that were matched

        # Keep all labels for a key so repeated detections cannot reuse one.
        gt_lookup: Dict[Tuple[str, Any], List[GroundTruthRecord]] = {}
        for gt in ground_truth:
            key = (gt.issue_type, gt.entity_id)
            gt_lookup.setdefault(key, []).append(gt)

        # Also build issue_type -> list of GT records (for type-level matching)
        gt_by_type: Dict[str, List[GroundTruthRecord]] = {}
        for gt in ground_truth:
            gt_by_type.setdefault(gt.issue_type, []).append(gt)

        # Build detected lookup by (issue_type, entity_id)
        det_by_type: Dict[str, List[DetectedIssue]] = {}
        for det in detected:
            det_by_type.setdefault(det.issue_type, []).append(det)

        tp_issue_ids: List[str] = []
        fp_issue_ids: List[str] = []
        fn_issue_ids: List[str] = []

        # Annotate detected issues with ground_truth_match flag
        for det in detected:
            key = (det.issue_type, det.entity_id)
            unmatched = next(
                (
                    gt
                    for gt in gt_lookup.get(key, [])
                    if gt.issue_id not in gt_matched
                ),
                None,
            )
            if unmatched is not None:
                det.ground_truth_match = True
                gt_matched.add(unmatched.issue_id)
                tp_issue_ids.append(det.issue_id)
            else:
                det.ground_truth_match = False
                fp_issue_ids.append(det.issue_id)

        # Find undetected GT records
        for gt in ground_truth:
            if gt.issue_id not in gt_matched:
                fn_issue_ids.append(gt.issue_id)

        tp = len(tp_issue_ids)
        fp = len(fp_issue_ids)
        fn = len(fn_issue_ids)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)

        # Per-type breakdown
        per_type: Dict[str, Dict] = {}
        all_types = set(det_by_type.keys()) | set(gt_by_type.keys())
        for itype in all_types:
            gt_count = len(gt_by_type.get(itype, []))
            det_count = len(det_by_type.get(itype, []))
            # TP for this type: detected with GT match for this type
            type_tp = sum(
                1 for d in det_by_type.get(itype, [])
                if d.ground_truth_match
            )
            type_fp = det_count - type_tp
            type_fn = max(0, gt_count - type_tp)
            per_type[itype] = {
                "gt_count": gt_count,
                "detected_count": det_count,
                "tp": type_tp,
                "fp": type_fp,
                "fn": type_fn,
            }

        result = EvaluationResult(
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1, 4),
            detected_count=len(detected),
            ground_truth_count=len(ground_truth),
            tp_issues=tp_issue_ids,
            fp_issues=fp_issue_ids,
            fn_issues=fn_issue_ids,
            per_type=per_type,
        )

        logger.info(
            "Evaluation: TP=%d FP=%d FN=%d Precision=%.4f Recall=%.4f F1=%.4f",
            tp, fp, fn, precision, recall, f1,
        )
        return result

    def validation_summary(
        self,
        detected: List[DetectedIssue],
        ground_truth: List[GroundTruthRecord],
        total_records_checked: int,
    ) -> Dict:
        """Return a high-level validation summary dict."""
        tp = sum(1 for d in detected if d.ground_truth_match is True)
        fp = sum(1 for d in detected if d.ground_truth_match is False)
        undetected = sum(
            1 for gt in ground_truth
            if not any(
                d.ground_truth_match and d.issue_type == gt.issue_type
                and d.entity_id == gt.entity_id
                for d in detected
            )
        )
        return {
            "total_records_checked": total_records_checked,
            "valid_records": total_records_checked - len(detected),
            "detected_anomalies": len(detected),
            "undetected_injected_anomalies": undetected,
            "false_positives": fp,
            "true_positives": tp,
            "false_negatives": len(ground_truth) - tp,
            "reconciliation_failures": len(
                [d for d in detected if d.issue_type == "BALANCE_DISAGREES_LEDGER"]
            ),
        }
