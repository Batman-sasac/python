def get_chosung(text):
    """한글 단어에서 초성만 추출하는 함수"""
    CHOSUNG_LIST = [
        'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 
        'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    ]
    result = ""
    for char in text:
        if '가' <= char <= '힣':
            # 한글 유니코드 공식: (한글 유니코드 - 0xAC00) // 588
            chosung_index = (ord(char) - 0xAC00) // 588
            result += CHOSUNG_LIST[chosung_index]
        else:
            result += char # 한글이 아니면 그대로 (공백, 숫자 등)
    return result