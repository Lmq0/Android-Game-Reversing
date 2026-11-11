import urllib.parse
import json
import re
import os

def parse_and_save(filepath):
    print(f"========== 正在解析: {filepath} ==========")
    
    try:
        # 1. 强行用 latin-1 读取，把所有字节原封不动读进来
        with open(filepath, 'r', encoding='latin-1', errors='ignore') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ 找不到文件: {filepath}")
        return

    # 2. 终极过滤：把所有 \x00 (空字符) 直接删掉！
    content = content.replace('\x00', '')

    # 3. 去掉了干扰，现在的 content 已经是正常的文本了
    # 我们再用正则，把每一行的十六进制数据精准抓出来
    # 匹配模式：8个数字开头的行，抓取后面的十六进制对，直到遇到非十六进制
    hex_string = ""
    lines = content.split('\n')
    for line in lines:
        # 找到这一行里所有的十六进制数字组合
        matches = re.findall(r'\b[0-9A-Fa-f]{2}\b', line)
        # 一个标准的行有 16 个字节，偏移地址不算，所以匹配出来大概有 16-24 个元素
        # 我们只取前 16 个，防止把右边的乱码也抓进来
        if len(matches) > 3: # 至少有几个才处理
            hex_string += "".join(matches[:16])

    print(f"🔍 提纯后的 Hex 长度: {len(hex_string)} 个字符 (约 {len(hex_string)//2} 字节)")

    if len(hex_string) < 20:
        print("❌ 提取的十六进制数据过短，请检查文件。")
        return

    # 4. 将纯十六进制转为字符串
    try:
        raw_bytes = bytes.fromhex(hex_string)
        raw_text = raw_bytes.decode('ascii', errors='ignore')
    except ValueError as e:
        print(f"❌ 十六进制数据转换失败: {e}")
        return
    
    # 5. 寻找有效载荷起点
    start_idx = raw_text.find('bv=')
    if start_idx == -1:
        print("❌ 未在提取的数据中找到 'bv='。")
        return
        
    payload_str = raw_text[start_idx:].strip()
    payload_str = payload_str.split('\n')[0]

    try:
        decoded_payload = urllib.parse.unquote(payload_str)
        match = re.search(r'request=(\[.*?\])(?:&seq=|$)', decoded_payload, re.DOTALL)
        
        if match:
            json_str = match.group(1)
            json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
            
            parsed_json = json.loads(json_str)
            
            base_name = os.path.basename(filepath).split('_')[0] 
            output_filename = f"{base_name}_parsed.json"
            
            with open(output_filename, 'w', encoding='utf-8') as out_f:
                json.dump(parsed_json, out_f, indent=4, ensure_ascii=False)
            
            print(f"✅ 解析成功！JSON 已保存至: {output_filename}\n")
            
        else:
            print("❌ 未找到 request 的 JSON 数据")
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        print(f"被污染的字符串片段: {decoded_payload[:200]}...")

if __name__ == "__main__":
    parse_and_save('attack_hex_output.txt')
    parse_and_save('pet_update_hex_output.txt')