import os, re, json, subprocess, urllib.parse, requests
from mutagen.mp3 import MP3

GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip()
TOPIC = os.environ.get("TOPIC", "Sự thật tâm lý học hành vi")
STRATEGY_RULES = os.environ.get("STRATEGY_RULES", "")
ROW_INDEX = os.environ.get("ROW_INDEX", "0")
GAS_WEBHOOK = os.environ.get("GAS_WEBHOOK_URL", "")

def extract_json(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f"Không tìm thấy JSON hợp lệ: {text[:200]}")
    return json.loads(match.group(0))

# 1. MULTI-AGENT: SÁNG TẠO KỊCH BẢN SIÊU TỐC QUA GROQ (LLAMA 3.3 70B)
def run_multi_agent_script(topic, rules):
    prompt = f"""Bạn là hệ thống 4 chuyên gia AI sản xuất YouTube Shorts kiếm tiền bền vững:
    1. DATA ANALYST: Tuân thủ quy tắc tối ưu từ dữ liệu kênh: "{rules}".
    2. CONTENT CREATOR: Viết kịch bản về "{topic}" theo lối kể chuyện phân tích chuyên sâu, giàu giá trị thực tế. Tránh liệt kê khô khan để không bị lỗi Repetitious Content.
    3. RETENTION OPTIMIZER:
       - 3 giây đầu (Hook): Đánh thẳng vào sự tò mò hoặc hiểu lầm phổ biến.
       - Câu cuối cùng: Nối mượt với câu mở đầu để tạo vòng lặp vô tận (Seamless Loop).
    4. COMPLIANCE AUDITOR: Loại bỏ từ ngữ nhạy cảm/bạo lực. Chọn giọng đọc và tốc độ phù hợp.

    Trả về duy nhất 1 JSON thuần (không giải thích) theo cấu trúc:
    {{
      "title": "Tiêu đề hấp dẫn dưới 60 ký tự kèm #Shorts",
      "description": "Mô tả ngắn giá trị video kèm 5 hashtag",
      "voice_text": "Lời thoại tiếng Việt tự nhiên (110-130 từ, không emoji, không ký tự đặc biệt)",
      "voice_gender": "female hoặc male",
      "voice_rate": "+5% hoặc +10% hoặc +0%",
      "image_prompts": [
        "Scene 1 detailed cinematic prompt in English, no text",
        "Scene 2 detailed cinematic prompt in English, no text",
        "Scene 3 detailed cinematic prompt in English, no text",
        "Scene 4 detailed cinematic prompt in English, no text"
      ]
    }}"""

    if GROQ_KEY:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.7
            },
            timeout=30
        ).json()
        if "choices" in res:
            return extract_json(res["choices"][0]["message"]["content"])
        print("Groq báo lỗi, chuyển sang cổng dự phòng:", res)

    # Cổng dự phòng 0 đồng không cần API Key
    fallback = requests.post(
        "https://text.pollinations.ai/",
        json={"messages": [{"role": "user", "content": prompt}], "model": "openai"},
        timeout=60
    )
    return extract_json(fallback.text)

# 2. SẢN XUẤT 4 ẢNH ĐỘC BẢN 9:16 (0% BẢN QUYỀN)
def generate_images(prompts):
    img_paths = []
    for idx, p in enumerate(prompts[:4]):
        safe_p = f"Vertical 9:16 original digital art, cinematic lighting, high detail, no text, no watermark: {p}"
        path = f"scene_{idx}.png"
        encoded = urllib.parse.quote(safe_p)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={idx+2026}"
        img_data = requests.get(url, timeout=90).content
        with open(path, "wb") as f:
            f.write(img_data)
        img_paths.append(path)
    return img_paths

# 3. TẠO GIỌNG ĐỌC BIẾN THIÊN & PHỤ ĐỀ CHUẨN GIÂY
def generate_voice(script_data):
    voice = "vi-VN-HoaiMyNeural" if script_data.get("voice_gender") == "female" else "vi-VN-NamMinhNeural"
    rate = script_data.get("voice_rate", "+5%")
    subprocess.run([
        "edge-tts", "--voice", voice, f"--rate={rate}",
        "--text", script_data["voice_text"],
        "--write-media", "voice.mp3", "--write-subtitles", "subs.vtt"
    ], check=True)
    return MP3("voice.mp3").info.length

# 4. DỰNG VIDEO FFMPEG + NHẠC NỀN THUẬT TOÁN (0% CONTENT ID)
def render_video(img_paths, duration):
    sec_per_img = duration / len(img_paths)
    clip_paths = []
    motions = [
        "z='min(zoom+0.0012,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "z='if(eq(on,1),1.18,max(1.0,zoom-0.0012))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    ]

    for idx, img in enumerate(img_paths):
        clip = f"clip_{idx}.mp4"
        frames = int(sec_per_img * 30)
        vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan={motions[idx % 2]}:d={frames}:s=1080x1920:fps=30"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", img,
            "-vf", vf, "-t", str(sec_per_img), "-pix_fmt", "yuv420p", clip
        ], check=True)
        clip_paths.append(clip)

    with open("concat.txt", "w") as f:
        for c in clip_paths:
            f.write(f"file '{c}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"aevalsrc='0.03*sin(2*PI*110*t)+0.02*sin(2*PI*165*t)':d={duration}",
        "ambient_bgm.wav"
    ], check=True)

    sub_style = "Alignment=2,MarginV=280,FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
        "-i", "voice.mp3", "-i", "ambient_bgm.wav",
        "-filter_complex", f"[0:v]subtitles=subs.vtt:force_style='{sub_style}'[v];[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", "final_short.mp4"
    ], check=True)

# 5. ĐĂNG YOUTUBE KÈM NHÃN MINH BẠCH AI
def upload_youtube(title, description):
    token_res = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"
    }).json()

    if "access_token" not in token_res:
        raise RuntimeError(f"Lỗi xác thực YouTube Token: {json.dumps(token_res, ensure_ascii=False)}")

    access_token = token_res["access_token"]
    metadata = {
        "snippet": {"title": title, "description": description, "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    }
    init_res = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=metadata
    )
    if init_res.status_code not in (200, 201):
        raise RuntimeError(f"Lỗi khởi tạo upload YouTube: {init_res.text}")

    with open("final_short.mp4", "rb") as f:
        vid_res = requests.put(init_res.headers["Location"], headers={"Content-Type": "video/mp4"}, data=f).json()
    return f"https://youtube.com/shorts/{vid_res['id']}"

if __name__ == "__main__":
    data = run_multi_agent_script(TOPIC, STRATEGY_RULES)
    print("Đã tạo xong kịch bản:", data["title"])
    imgs = generate_images(data["image_prompts"])
    dur = generate_voice(data)
    render_video(imgs, dur)
    yt_url = upload_youtube(data["title"], data["description"])
    print("ĐÃ ĐĂNG THÀNH CÔNG:", yt_url)
    if GAS_WEBHOOK:
        requests.post(GAS_WEBHOOK, json={"row": ROW_INDEX, "title": data["title"], "url": yt_url})
