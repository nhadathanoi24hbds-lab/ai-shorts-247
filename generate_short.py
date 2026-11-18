import os, re, json, subprocess, urllib.parse, requests
from concurrent.futures import ThreadPoolExecutor
from mutagen.mp3 import MP3
from gtts import gTTS

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

# 1. TẠO KỊCH BẢN SIÊU TỐC (~1 GIÂY)
def run_multi_agent_script(topic, rules):
    prompt = f"""Bạn là hệ thống 4 chuyên gia AI sản xuất YouTube Shorts:
    1. DATA ANALYST: Áp dụng quy tắc: "{rules}".
    2. CONTENT CREATOR: Viết kịch bản về "{topic}" theo lối kể chuyện phân tích sâu, tránh liệt kê khô khan.
    3. RETENTION OPTIMIZER: 3 giây đầu gây tò mò mạnh; câu cuối nối mượt về câu đầu tạo vòng lặp.
    4. COMPLIANCE AUDITOR: Không từ ngữ nhạy cảm.

    Chỉ trả về 1 JSON thuần:
    {{
      "title": "Tiêu đề hấp dẫn dưới 60 ký tự kèm #Shorts",
      "description": "Mô tả ngắn kèm 5 hashtag",
      "voice_text": "Lời thoại tiếng Việt tự nhiên (110-130 từ, không emoji, không ký tự đặc biệt)",
      "voice_gender": "female hoặc male",
      "voice_rate": "+5% hoặc +10%",
      "image_prompts": [
        "Scene 1 cinematic vertical art in English, no text",
        "Scene 2 cinematic vertical art in English, no text",
        "Scene 3 cinematic vertical art in English, no text",
        "Scene 4 cinematic vertical art in English, no text"
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
            timeout=20
        ).json()
        if "choices" in res:
            return extract_json(res["choices"][0]["message"]["content"])

    fallback = requests.post(
        "https://text.pollinations.ai/",
        json={"messages": [{"role": "user", "content": prompt}], "model": "openai"},
        timeout=35
    )
    return extract_json(fallback.text)

# 2. TẢI SONG SONG 4 ẢNH CÙNG LÚC (~12 GIÂY)
def download_one_image(args):
    idx, p = args
    safe_p = f"Vertical 9:16 digital art, cinematic lighting, high detail, no text: {p}"
    path = f"scene_{idx}.png"
    encoded = urllib.parse.quote(safe_p)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=720&height=1280&nologo=true&seed={idx+2026}"
    img_data = requests.get(url, timeout=45).content
    with open(path, "wb") as f:
        f.write(img_data)
    return path

def generate_images(prompts):
    with ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(download_one_image, enumerate(prompts[:4])))

# Tạo phụ đề VTT tự động khớp thời lượng nếu dùng gTTS dự phòng
def format_vtt_time(seconds):
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hrs:02d}:{mins:02d}:{secs:06.3f}"

def build_vtt_subtitles(text, total_duration, filename="subs.vtt"):
    words = text.split()
    chunk_size = 9
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    total_chars = sum(len(c) for c in chunks) or 1
    current_time = 0.0

    with open(filename, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for idx, chunk in enumerate(chunks):
            dur = (len(chunk) / total_chars) * total_duration
            start_str = format_vtt_time(current_time)
            end_str = format_vtt_time(min(current_time + dur, total_duration))
            f.write(f"{idx + 1}\n{start_str} --> {end_str}\n{chunk}\n\n")
            current_time += dur

# 3. TẠO GIỌNG ĐỌC (ƯU TIÊN EDGE-TTS, TỰ ĐỘNG DỰ PHÒNG SANG GOOGLE TTS)
def generate_voice(script_data):
    text = script_data["voice_text"].strip()
    voice = "vi-VN-HoaiMyNeural" if script_data.get("voice_gender") == "female" else "vi-VN-NamMinhNeural"
    rate = script_data.get("voice_rate", "+5%")

    try:
        subprocess.run([
            "edge-tts", "--voice", voice, f"--rate={rate}",
            "--text", text,
            "--write-media", "voice.mp3", "--write-subtitles", "subs.vtt"
        ], check=True)
        return MP3("voice.mp3").info.length
    except Exception:
        print("Edge-TTS tạm chặn IP, tự động chuyển sang Google TTS dự phòng...")
        tts = gTTS(text=text, lang="vi", slow=False)
        tts.save("raw_voice.mp3")
        # Tăng nhẹ tốc độ 1.12x cho nhịp điệu Shorts cuốn hút
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", "raw_voice.mp3",
            "-filter:a", "atempo=1.12", "voice.mp3"
        ], check=True)
        dur = MP3("voice.mp3").info.length
        build_vtt_subtitles(text, dur, "subs.vtt")
        return dur

# 4. DỰNG VIDEO SONG SONG 4 CLIP Ở CHUẨN HD 720x1280 (~15 GIÂY)
def render_one_clip(args):
    idx, img, sec_per_img = args
    clip = f"clip_{idx}.mp4"
    frames = int(sec_per_img * 25)
    motion = (
        "z='min(zoom+0.0015,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        if idx % 2 == 0 else
        "z='if(eq(on,1),1.15,max(1.0,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    )
    vf = f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,zoompan={motion}:d={frames}:s=720x1280:fps=25"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img,
        "-vf", vf, "-t", str(sec_per_img), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", clip
    ], check=True)
    return clip

def render_video(img_paths, duration):
    sec_per_img = duration / len(img_paths)
    tasks = [(i, img, sec_per_img) for i, img in enumerate(img_paths)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        clip_paths = list(executor.map(render_one_clip, tasks))

    with open("concat.txt", "w") as f:
        for c in clip_paths:
            f.write(f"file '{c}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", f"aevalsrc='0.03*sin(2*PI*110*t)+0.02*sin(2*PI*165*t)':d={duration}",
        "ambient_bgm.wav"
    ], check=True)

    sub_style = "Alignment=2,MarginV=180,FontSize=15,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt",
        "-i", "voice.mp3", "-i", "ambient_bgm.wav",
        "-filter_complex", f"[0:v]subtitles=subs.vtt:force_style='{sub_style}'[v];[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", "final_short.mp4"
    ], check=True)

# 5. ĐĂNG YOUTUBE (~5 GIÂY)
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
    print("1. Xong kịch bản:", data["title"])
    imgs = generate_images(data["image_prompts"])
    print("2. Xong 4 ảnh")
    dur = generate_voice(data)
    print("3. Xong giọng đọc")
    render_video(imgs, dur)
    print("4. Xong render video")
    yt_url = upload_youtube(data["title"], data["description"])
    print("5. ĐÃ ĐĂNG THÀNH CÔNG:", yt_url)
    if GAS_WEBHOOK:
        requests.post(GAS_WEBHOOK, json={"row": ROW_INDEX, "title": data["title"], "url": yt_url})
