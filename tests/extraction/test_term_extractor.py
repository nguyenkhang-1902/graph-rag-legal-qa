"""Tests cho app/extraction/term_extractor.py (T012).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi
app/extraction/term_extractor.py ton tai - chay pytest luc nay phai FAIL
vi ModuleNotFoundError (bang chung "red" truoc khi implement "green").

Theo data-model.md:
  - DEFINES (Article -> Term): "... duoc hieu la ..." - rule-based CHI xu
    ly truong hop thuat ngu duoc trich dan ro rang (quotes) truoc cum tu
    nay - day la tin hieu manh, do chinh xac cao. Cac cau khong co quotes
    (chu ngu la mot menh de mo ta dai, khong phai mot thuat ngu don) BI BO
    QUA o rule-based (khong doan mo - "sai con te hon la khong trich
    xuat", cung triet ly voi reference_extractor.py) - de lai cho LLM
    fallback (chua lam trong T012 nay, xem ghi chu trong module).
  - USES_TERM (Article -> Term): string-match ten thuat ngu DA CO trong
    known_terms - CASE-SENSITIVE + word-boundary (tranh false positive tu
    tu thuong dung hang ngay trung voi thuat ngu viet hoa, vd "Ngay" dinh
    nghia nhung "ngay" xuat hien khap noi trong van ban voi nghia thong
    thuong).

Vi du dung trong test lay TRUC TIEP tu corpus that (data/raw/08_2016_tt-
bxd_1.md, 09_2016_tt-bxd_1.md) - xem TIEN_DO.md ĐỢT 5.
"""
from app.extraction.term_extractor import (
    ExtractedDefinition,
    TermUsage,
    extract_definitions_rule_based,
    extract_term_usages_rule_based,
)


# --- extract_definitions_rule_based -------------------------------------


def test_extracts_definition_with_curly_quotes_real_corpus_example():
    # Nguyen van tu data/raw/09_2016_tt-bxd_1.md - cau THAT noi 2 dinh
    # nghia qua "va", nhung CHI thuat ngu dau ("Ngay") co quotes, thuat
    # ngu thu hai ("thang") thi khong - rule-based dung lookahead " va
    # ...duoc hieu la" de cat dung truoc dinh nghia thu hai khong duoc
    # trich xuat (khong co quotes -> bi bo qua, xem module docstring).
    text = "1.19. “Ngày” được hiểu là ngày dương lịch và tháng được hiểu là tháng dương lịch."
    result = extract_definitions_rule_based(text)
    assert ExtractedDefinition(
        term_id="ngay", ten_thuat_ngu="Ngày", dinh_nghia="ngày dương lịch"
    ) in result
    assert len(result) == 1  # "thang" khong co quotes -> khong duoc trich


def test_extracts_definition_with_straight_quotes():
    text = '"Chất thải" được hiểu là vật chất được thải ra.'
    result = extract_definitions_rule_based(text)
    assert result == [
        ExtractedDefinition(
            term_id="chat-thai",
            ten_thuat_ngu="Chất thải",
            dinh_nghia="vật chất được thải ra",
        )
    ]


def test_extracts_multi_word_term_real_corpus_example():
    # Nguyen van tu data/raw/08_2016_tt-bxd_1.md.
    text = (
        "1. Trong Điều này, “Đơn PCT” được hiểu là Đơn đăng ký sáng chế "
        "nộp theo Hiệp ước PCT, bao gồm:"
    )
    result = extract_definitions_rule_based(text)
    assert len(result) == 1
    assert result[0].term_id == "don-pct"
    assert result[0].ten_thuat_ngu == "Đơn PCT"
    assert result[0].dinh_nghia.startswith("Đơn đăng ký sáng chế")


def test_extracts_multiple_definitions_in_order():
    text = '“A” được hiểu là định nghĩa A. “B” được hiểu là định nghĩa B.'
    result = extract_definitions_rule_based(text)
    assert [d.ten_thuat_ngu for d in result] == ["A", "B"]


def test_definition_boundary_stops_at_period_not_bleeding_into_next_sentence():
    text = '“A” được hiểu là định nghĩa A. Đây là câu tiếp theo không liên quan.'
    result = extract_definitions_rule_based(text)
    assert result[0].dinh_nghia == "định nghĩa A"
    assert "câu tiếp theo" not in result[0].dinh_nghia


def test_definition_boundary_stops_at_semicolon():
    text = "“A” được hiểu là định nghĩa A; còn B là chuyện khác."
    result = extract_definitions_rule_based(text)
    assert result[0].dinh_nghia == "định nghĩa A"


def test_unquoted_subject_before_duoc_hieu_la_is_skipped_real_corpus_example():
    # Nguyen van tu data/raw/103_2006_nđ-cp_21.md - chu ngu la mot menh de
    # mo ta dai (khong phai mot thuat ngu don, khong co quotes) - rule-based
    # PHAI bo qua (khong doan mo thuat ngu tu menh de dai nay).
    text = (
        "Sản phẩm được đưa ra thị trường, kể cả thị trường nước ngoài một "
        "cách hợp pháp quy định tại điểm b khoản 2 Điều 125 của Luật Sở "
        "hữu trí tuệ được hiểu là sản phẩm do chính chủ sở hữu."
    )
    assert extract_definitions_rule_based(text) == []


def test_no_duoc_hieu_la_returns_empty_list():
    assert extract_definitions_rule_based("Văn bản này không có định nghĩa nào.") == []


def test_empty_text_returns_empty_list():
    assert extract_definitions_rule_based("") == []


# --- mau danh sach danh so ("N. <thuat ngu> la <dinh nghia>") -----------
# Phat hien 2026-08-05 (TIEN_DO.md DOT 6): quet that 61,069 file cho thay
# day la mau PHO BIEN HON NHIEU (1,072 file co trigger "duoc hieu nhu
# sau") so voi mau co quotes (chi 54 file) - khong co quotes quanh thuat
# ngu, nhung cau truc RAT DEU DAN: moi muc trong danh sach la "N. <thuat
# ngu KHONG quotes> la <dinh nghia>." Chi kich hoat KHI van ban co cum
# trigger "duoc hieu nhu sau" (tranh false positive tren danh sach danh
# so KHAC khong phai dinh nghia, vd danh sach dieu kien).


def test_extracts_enum_list_definitions_real_corpus_example():
    # Nguyen van rut gon tu data/raw/01_2012_tt-nhnn_2.md.
    text = (
        "Điều 2. Giải thích từ ngữ\n\n"
        "Trong Thông tư này, các từ ngữ sau đây được hiểu như sau:\n"
        "1. Giấy tờ có giá là bằng chứng xác nhận nghĩa vụ trả nợ.\n"
        "2. Giấy tờ có giá dài hạn là giấy tờ có giá có thời hạn từ một năm trở lên.\n"
        "3. Giấy tờ có giá ngắn hạn là giấy tờ có giá có thời hạn dưới một năm."
    )
    result = extract_definitions_rule_based(text)
    assert len(result) == 3
    assert result[0] == ExtractedDefinition(
        term_id="giay-to-co-gia",
        ten_thuat_ngu="Giấy tờ có giá",
        dinh_nghia="bằng chứng xác nhận nghĩa vụ trả nợ.",
    )
    assert result[1].ten_thuat_ngu == "Giấy tờ có giá dài hạn"
    assert result[2].ten_thuat_ngu == "Giấy tờ có giá ngắn hạn"


def test_enum_list_definition_spans_multiple_lines_until_next_item():
    # Nguyen van tu data/raw/01_2011_qh13_2.md - dinh nghia muc 2 tiep tuc
    # sang dong thu hai (khong bat dau bang so thu tu moi) - phai duoc gom
    # HET vao dinh nghia cua muc 2, KHONG bi cat o dau dong.
    text = (
        "Trong Luật này, các từ ngữ dưới đây được hiểu như sau:\n"
        "1. Hoạt động lưu trữ là hoạt động thu thập, chỉnh lý.\n"
        "2. Tài liệu là vật mang tin được hình thành.\n"
        "Tài liệu bao gồm văn bản, dự án, bản vẽ thiết kế.\n"
        "3. Tài liệu lưu trữ là tài liệu có giá trị."
    )
    result = extract_definitions_rule_based(text)
    assert len(result) == 3
    assert result[1].ten_thuat_ngu == "Tài liệu"
    assert result[1].dinh_nghia == (
        "vật mang tin được hình thành.\nTài liệu bao gồm văn bản, dự án, "
        "bản vẽ thiết kế."
    )


def test_enum_list_last_item_captures_to_end_of_text():
    text = (
        "được hiểu như sau:\n"
        "1. A là định nghĩa A.\n"
        "2. B là định nghĩa B, có thể dài hai câu. Câu thứ hai vẫn thuộc mục 2."
    )
    result = extract_definitions_rule_based(text)
    assert result[1].dinh_nghia == "định nghĩa B, có thể dài hai câu. Câu thứ hai vẫn thuộc mục 2."


def test_enum_list_pattern_requires_trigger_phrase_to_avoid_false_positive():
    # Danh sach danh so nhung KHONG phai dinh nghia (dieu kien) va KHONG
    # co trigger "duoc hieu nhu sau" - khong duoc trich, tranh false
    # positive tren cau truc "N. X la Y" xuat hien ngau nhien trong danh
    # sach dieu kien/thu tuc.
    text = (
        "Điều kiện được cấp phép bao gồm:\n"
        "1. Có quốc tịch Việt Nam là điều kiện bắt buộc.\n"
        "2. Có năng lực hành vi dân sự đầy đủ là điều kiện thứ hai."
    )
    assert extract_definitions_rule_based(text) == []


def test_enum_list_skips_la_inside_abbreviation_parenthesis():
    # Bug that phat hien khi kiem chung tren toan bo corpus (TIEN_DO.md
    # DOT 6, ~4.4% dinh nghia bi anh huong): mau "<Ten day du> (sau day
    # goi tat la <ten ngan>) la <dinh nghia>" - " la " DAU TIEN nam BEN
    # TRONG ngoac viet tat, khong phai ranh gioi that giua thuat ngu va
    # dinh nghia. Phai bo qua " la " nao ma phan truoc no co ngoac mo CHUA
    # dong (mat can bang), tim " la " tiep theo SAU khi ngoac da dong.
    text = (
        "được hiểu như sau:\n"
        "1. Cơ sở bán lẻ thuốc trong bệnh viện (sau đây gọi tắt là cơ sở "
        "bán lẻ thuốc) là cơ sở bán lẻ thuốc trong khuôn viên bệnh viện."
    )
    result = extract_definitions_rule_based(text)
    assert len(result) == 1
    assert result[0].ten_thuat_ngu == (
        "Cơ sở bán lẻ thuốc trong bệnh viện (sau đây gọi tắt là cơ sở bán lẻ thuốc)"
    )
    assert result[0].dinh_nghia == "cơ sở bán lẻ thuốc trong khuôn viên bệnh viện."


def test_combines_quoted_pattern_and_enum_list_pattern_without_duplicate_term_id():
    text = (
        '“Ngày” được hiểu là ngày dương lịch.\n\n'
        "được hiểu như sau:\n"
        "1. Tài liệu là vật mang tin.\n"
        "2. Ngày là ngày dương lịch (định nghĩa trùng term_id với ở trên)."
    )
    result = extract_definitions_rule_based(text)
    term_ids = [d.term_id for d in result]
    assert term_ids.count("ngay") == 1  # khong trung lap, giu lan dau tien
    assert "tai-lieu" in term_ids


# --- extract_term_usages_rule_based --------------------------------------


def test_finds_known_term_used_in_text():
    known_terms = {"ngay": "Ngày"}
    text = "Thời hạn được tính theo Ngày làm việc."
    result = extract_term_usages_rule_based(text, known_terms)
    assert result == [TermUsage(term_id="ngay", ten_thuat_ngu="Ngày")]


def test_case_sensitive_does_not_match_lowercase_common_word():
    # "ngay" (thuong, tu thong dung hang ngay) KHONG duoc khop voi thuat
    # ngu da dinh nghia "Ngày" (viet hoa) - tranh bung no false positive
    # USES_TERM tren tu thong dung.
    known_terms = {"ngay": "Ngày"}
    text = "Trong ngày hôm nay, không có gì đặc biệt xảy ra."
    assert extract_term_usages_rule_based(text, known_terms) == []


def test_word_boundary_does_not_match_substring_inside_longer_word():
    known_terms = {"don": "Đơn"}
    text = "Đơngiản là một từ không tồn tại thật nhưng dùng để test ranh giới từ."
    assert extract_term_usages_rule_based(text, known_terms) == []


def test_multiple_known_terms_returns_only_matches_in_order_of_first_occurrence():
    known_terms = {"a": "A", "b": "B", "c": "C"}
    # "C" KHONG duoc nhac toi trong text - kiem tra chi tra ve thuat ngu
    # thuc su xuat hien.
    text = "Văn bản nhắc tới B trước, rồi mới nhắc tới A."
    result = extract_term_usages_rule_based(text, known_terms)
    assert [u.ten_thuat_ngu for u in result] == ["B", "A"]


def test_empty_known_terms_returns_empty_list():
    assert extract_term_usages_rule_based("Bất kỳ văn bản nào.", {}) == []


def test_empty_text_returns_empty_list_for_usages():
    known_terms = {"a": "A"}
    assert extract_term_usages_rule_based("", known_terms) == []


def test_each_known_term_matched_at_most_once_even_if_repeated_in_text():
    known_terms = {"ngay": "Ngày"}
    text = "Ngày làm việc và Ngày nghỉ đều là Ngày."
    result = extract_term_usages_rule_based(text, known_terms)
    assert result == [TermUsage(term_id="ngay", ten_thuat_ngu="Ngày")]
