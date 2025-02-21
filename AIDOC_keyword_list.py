text_fix = [
    "บทดัดย่อ",  # 'ค' -> 'ด' mistake
    "บทดัคย่อ",  # 'ต' -> 'ด' mistake
    "บทตัดย่อ",  # 'ค' -> 'ต' mistake
    "บทคัตย่อ",  # OCR often misreads 'ด' as 'ต'
    "บทคัดยอ",   # Missing '่' due to OCR error
    "บทคัดย่อะ", # Extra character at the end
    "บทคัดั่อ",  # OCR swapping diacritics
    "บทคักย่อ",  # Misreading 'ด' as 'ก'
    "บทคัตยอ",   # Combining 'ต' and missing '่'
    "บทคัทย่อ",  # Missing 'ด'
    "บทคัทยอ",   # Missing 'ด' and '่'
    "บทคัดย๊อ",  # '่' replaced with '๊'
    "บทคัดแย่อ", # 'ย' mistakenly duplicated
]
