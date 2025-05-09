import os
from fastapi import FastAPI, Query # Thêm Query để định nghĩa tham số tùy chọn
from fastapi.middleware.cors import CORSMiddleware
import requests
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime, timedelta
import re
import urllib.parse

# ... (Phần load_dotenv và khởi tạo Gemini, FastAPI giữ nguyên) ...
load_dotenv()
google_ai_api_key = os.getenv("GOOGLE_AI_API_KEY")
weather_api_key = os.getenv("OPENWEATHERMAP_API_KEY")

if not google_ai_api_key:
    print("Lỗi: GOOGLE_AI_API_KEY chưa được thiết lập trong file .env")
    exit()
if not weather_api_key:
    print("Lỗi: OPENWEATHERMAP_API_KEY chưa được thiết lập trong file .env")
    exit()

genai.configure(api_key=google_ai_api_key)
gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- HẾT PHẦN KHÔNG THAY ĐỔI ---

def get_weather_data(city, api_key, type="weather"):
    # ... (Giữ nguyên hàm này) ...
    if type == "weather":
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=vi"
    elif type == "forecast":
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric&lang=vi"
    else:
        return None, "Loại API không hợp lệ"
    try:
        r = requests.get(url)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.HTTPError as http_err:
        if r.status_code == 404:
            return None, f"Không tìm thấy thành phố '{city}'."
        elif r.status_code == 401:
            return None, "Lỗi xác thực API Key của OpenWeatherMap."
        return None, f"Lỗi HTTP: {http_err} (mã lỗi: {r.status_code})"
    except requests.exceptions.RequestException as req_err:
        return None, f"Lỗi kết nối: {req_err}"
    except Exception as e:
        return None, f"Lỗi không xác định khi gọi API thời tiết: {e}"

def analyze_user_intent_with_gemini(question: str):
    """
    Phân tích câu hỏi của người dùng để xác định ý định, thành phố và các thông tin khác.
    """
    prompt = f"""
    Bạn là một trợ lý AI phân tích câu hỏi.
    Hãy phân tích câu hỏi sau và trích xuất các thông tin:
    1. city: Tên thành phố (Nếu có và rõ ràng, ví dụ "Huế" trong "Đại Nội Huế"). Nếu không có thành phố cụ thể trong câu hỏi nhưng có một địa điểm rõ ràng, để trống city.
    2. place_name: Tên địa điểm cụ thể nếu người dùng muốn tìm hoặc hỏi đường đến (ví dụ: "Đại Nội Huế", "Hồ Gươm").
    3. intent: Mục đích của câu hỏi. Các giá trị có thể:
        - "current_weather": Hỏi thời tiết hiện tại.
        - "clothing_advice_today": Hỏi nên mặc gì hôm nay.
        - "forecast_tomorrow": Hỏi thời tiết ngày mai.
        - "clothing_advice_tomorrow": Hỏi nên mặc gì ngày mai.
        - "forecast_next_days": Hỏi thời tiết nhiều ngày tới.
        - "place_recommendation": Hỏi gợi ý địa điểm du lịch/vui chơi chung chung ở một thành phố.
        - "specific_place_navigation": Hỏi đường đi hoặc thông tin về một địa điểm CỤ THỂ (ví dụ: "chỉ đường đến Đại Nội Huế", "tìm Hồ Gươm trên bản đồ").
        - "unknown": Nếu không thể xác định rõ ràng.
    4. num_days: Số ngày muốn dự báo.

    Câu hỏi: "{question}"

    Trả lời theo định dạng sau (CHỈ TRẢ VỀ CHUỖI NÀY, KHÔNG GIẢI THÍCH GÌ THÊM):
    CITY:[tên thành phố]
    PLACE_NAME:[tên địa điểm]
    INTENT:[ý định]
    NUM_DAYS:[số ngày]
    """
    try:
        response = gemini_model.generate_content(prompt)
        analysis = response.text.strip()
        # print(f"Gemini Raw Analysis:\n{analysis}") # Debug

        city = (re.search(r"CITY:(.*)", analysis, re.IGNORECASE).group(1).strip()
                if re.search(r"CITY:(.*)", analysis, re.IGNORECASE) else "")
        place_name = (re.search(r"PLACE_NAME:(.*)", analysis, re.IGNORECASE).group(1).strip()
                      if re.search(r"PLACE_NAME:(.*)", analysis, re.IGNORECASE) else "")
        intent = (re.search(r"INTENT:(.*)", analysis, re.IGNORECASE).group(1).strip()
                  if re.search(r"INTENT:(.*)", analysis, re.IGNORECASE) else "unknown")
        num_days_match = re.search(r"NUM_DAYS:(\d*)", analysis, re.IGNORECASE)
        num_days = int(num_days_match.group(1)) if num_days_match and num_days_match.group(1) else 1
        
        # Nếu intent là specific_place_navigation mà không có place_name, thử trích xuất lại place_name
        if intent == "specific_place_navigation" and not place_name:
            # Đơn giản là lấy toàn bộ câu hỏi làm place_name nếu nó không quá chung chung
            # Hoặc dùng một prompt khác để trích xuất place_name kỹ hơn
            # Ví dụ đơn giản:
            if "đến" in question.lower():
                 extracted_place = question.lower().split("đến", 1)[-1].strip()
                 # Có thể cần làm sạch thêm
                 place_name = extracted_place.replace("?", "").strip().title()


        # Nếu có place_name nhưng không có city, thử trích xuất city từ place_name (ví dụ: "Đại Nội Huế" -> city "Huế")
        if place_name and not city:
            city_extract_prompt_from_place = f"Từ tên địa điểm '{place_name}', trích xuất tên thành phố nếu có. Nếu không rõ thành phố, trả về 'Không xác định'. Chỉ trả về tên thành phố."
            city_response = gemini_model.generate_content(city_extract_prompt_from_place)
            extracted_city = city_response.text.strip()
            if extracted_city and extracted_city.lower() != "không xác định":
                city = extracted_city
        
        # Nếu vẫn không có city và intent cần city (trừ place_recommendation và specific_place_navigation nếu đã có place_name)
        # thì thử trích xuất city từ câu hỏi gốc.
        if not city and intent not in ["unknown", "place_recommendation", "specific_place_navigation"] or \
           (intent in ["place_recommendation", "specific_place_navigation"] and not place_name and not city):
            city_extract_prompt = f"Trích xuất tên thành phố từ câu sau: \"{question}\". Chỉ trả về tên thành phố. Nếu không có, trả về 'Không xác định'."
            city_response = gemini_model.generate_content(city_extract_prompt)
            extracted_city_name = city_response.text.strip()
            if extracted_city_name.lower() != "không xác định" and extracted_city_name:
                city = extracted_city_name
        
        # print(f"Parsed: City='{city}', Place='{place_name}', Intent='{intent}'") # Debug
        return {"city": city, "place_name": place_name, "intent": intent, "num_days": num_days}

    except Exception as e:
        print(f"Lỗi khi phân tích ý định bằng Gemini: {e}")
        return {"city": "", "place_name": "", "intent": "unknown", "num_days": 1}


# ... (format_current_weather, format_daily_forecast, get_clothing_advice giữ nguyên) ...
def format_current_weather(data, city_name_override=None):
    main_data = data.get("main")
    weather_list = data.get("weather")
    city_name_from_api = data.get("name", "Thành phố này")
    display_city_name = city_name_override if city_name_override else city_name_from_api

    if not main_data or not weather_list or not weather_list[0]:
        return f"Dữ liệu thời tiết cho {display_city_name} không đầy đủ.", None
    temp = main_data.get("temp")
    feels_like = main_data.get("feels_like")
    humidity = main_data.get("humidity")
    desc = weather_list[0].get("description")
    icon = weather_list[0].get("icon")
    if temp is None or desc is None:
        return f"Không thể lấy thông tin nhiệt độ hoặc mô tả cho {display_city_name}.", None
    weather_info_for_clothing = {"temp": temp, "feels_like": feels_like, "description": desc, "humidity": humidity, "icon": icon}
    return (f"Hiện tại ở {display_city_name}: {desc}, nhiệt độ {temp}°C (cảm giác như {feels_like}°C), độ ẩm {humidity}%.", weather_info_for_clothing)

intent_details_holder = {}

def format_daily_forecast(forecast_data, num_days, city_name_override=None):
    if 'list' not in forecast_data:
        return "Không có dữ liệu dự báo.", None
    daily_summary = {}
    city_name_from_api = forecast_data.get("city", {}).get("name", "Thành phố này")
    display_city_name = city_name_override if city_name_override else city_name_from_api
    current_intent_details = intent_details_holder.get("details", {})
    for item in forecast_data['list']:
        date_txt = item['dt_txt'].split(' ')[0]
        if len(daily_summary) >= num_days and date_txt not in daily_summary:
            if num_days == 1 and datetime.strptime(date_txt, "%Y-%m-%d").date() > (datetime.now() + timedelta(days=1)).date(): break
            elif len(daily_summary) >= num_days: break
        if date_txt not in daily_summary:
            if datetime.strptime(date_txt, "%Y-%m-%d").date() == datetime.now().date():
                if num_days == 1 and current_intent_details.get("intent") in ["forecast_tomorrow", "clothing_advice_tomorrow"]: continue
            daily_summary[date_txt] = {'temps': [], 'feels_like_temps': [], 'humidity': [], 'descriptions': {}, 'icons': {}}
        daily_summary[date_txt]['temps'].append(item['main']['temp'])
        daily_summary[date_txt]['feels_like_temps'].append(item['main']['feels_like'])
        daily_summary[date_txt]['humidity'].append(item['main']['humidity'])
        desc = item['weather'][0]['description']
        icon = item['weather'][0]['icon']
        daily_summary[date_txt]['descriptions'][desc] = daily_summary[date_txt]['descriptions'].get(desc, 0) + 1
        daily_summary[date_txt]['icons'][icon] = daily_summary[date_txt]['icons'].get(icon, 0) + 1
    output_str = f"Dự báo thời tiết cho {display_city_name}:\n"
    weather_for_clothing_tomorrow = None
    processed_days_count = 0
    sorted_dates = sorted(daily_summary.keys())
    for date_str in sorted_dates:
        if processed_days_count >= num_days: break
        current_date_obj = datetime.now().date()
        forecast_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        if current_intent_details.get("intent") in ["forecast_tomorrow", "clothing_advice_tomorrow"] and forecast_date_obj <= current_date_obj: continue
        if current_intent_details.get("intent") == "forecast_next_days" and forecast_date_obj <= current_date_obj: continue
        day_data = daily_summary[date_str]
        if not day_data['temps']: continue
        min_temp, max_temp = min(day_data['temps']), max(day_data['temps'])
        avg_humidity = sum(day_data['humidity']) / len(day_data['humidity'])
        common_desc = max(day_data['descriptions'], key=day_data['descriptions'].get)
        common_icon = max(day_data['icons'], key=day_data['icons'].get)
        formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m")
        date_label = formatted_date
        if forecast_date_obj == (datetime.now() + timedelta(days=1)).date():
            date_label = "Ngày mai (" + formatted_date + ")"
            weather_for_clothing_tomorrow = {"temp_min": min_temp, "temp_max": max_temp, "description": common_desc, "humidity": avg_humidity, "icon": common_icon}
        output_str += f"- {date_label}: {common_desc}, nhiệt độ từ {min_temp:.1f}°C - {max_temp:.1f}°C, độ ẩm khoảng {avg_humidity:.0f}%.\n"
        processed_days_count +=1
        if num_days == 1 and weather_for_clothing_tomorrow: break
    if not weather_for_clothing_tomorrow and num_days == 1 and current_intent_details.get("intent") in ["clothing_advice_tomorrow", "forecast_tomorrow"]:
        return f"Rất tiếc, tôi chưa có đủ dữ liệu dự báo chi tiết cho ngày mai tại {display_city_name}. Vui lòng thử lại sau.", None
    if processed_days_count == 0 and num_days > 0 :
         return f"Không có dữ liệu dự báo cho những ngày tới tại {display_city_name}.", None
    return output_str.strip(), weather_for_clothing_tomorrow

def get_clothing_advice(weather_info, day_description="hôm nay"):
    if not weather_info: return "Không có thông tin thời tiết để đưa ra lời khuyên."
    temp_desc = ""
    if "temp_min" in weather_info and "temp_max" in weather_info:
        temp_desc = f"nhiệt độ dao động từ {weather_info['temp_min']:.1f}°C đến {weather_info['temp_max']:.1f}°C"
    elif "temp" in weather_info:
        temp_desc = f"nhiệt độ khoảng {weather_info['temp']:.1f}°C"
        if "feels_like" in weather_info: temp_desc += f" (cảm giác như {weather_info['feels_like']:.1f}°C)"
    description = weather_info.get('description', 'không rõ')
    humidity = weather_info.get('humidity')
    humidity_desc = f", độ ẩm {humidity:.0f}%" if humidity else ""
    prompt = f"""Bạn là một stylist AI thân thiện. Dựa vào thông tin thời tiết sau, hãy đưa ra lời khuyên nên mặc gì. Thời tiết {day_description}: {description}, {temp_desc}{humidity_desc}. Hãy đưa ra gợi ý cụ thể. Lời khuyên của bạn:"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Lỗi khi lấy lời khuyên từ Gemini: {e}")
        return "Xin lỗi, tôi không thể đưa ra lời khuyên về trang phục lúc này."

def get_place_recommendations_from_gemini(city_name: str):
    # ... (Giữ nguyên hàm này) ...
    if not city_name:
        return "Vui lòng cung cấp tên thành phố để tôi có thể gợi ý địa điểm."
    prompt = f"""Bạn là một hướng dẫn viên du lịch AI. Hãy gợi ý từ 3 đến 5 địa điểm du lịch, tham quan hoặc vui chơi nổi tiếng ở thành phố "{city_name}". Liệt kê mỗi địa điểm trên một dòng mới. Chỉ trả về tên các địa điểm, không thêm mô tả hay đánh số."""
    try:
        response = gemini_model.generate_content(prompt)
        place_names_text = response.text.strip()
        if not place_names_text or "không tìm thấy thông tin" in place_names_text.lower() or "không có gợi ý" in place_names_text.lower():
             return f"Xin lỗi, tôi không tìm thấy gợi ý địa điểm nào cho {city_name} vào lúc này."
        place_names = [name.strip() for name in place_names_text.split('\n') if name.strip()]
        if not place_names:
            return f"Xin lỗi, tôi không thể đưa ra gợi ý địa điểm cụ thể cho {city_name}."
        html_output = f"<p>Dưới đây là một số gợi ý địa điểm ở {city_name} bạn có thể tham khảo:</p>\n<ul>\n"
        for name in place_names:
            clean_name = name.replace("*", "").strip()
            if not clean_name: continue
            encoded_name = urllib.parse.quote_plus(clean_name)
            map_link = f"https://www.google.com/maps/search/?api=1&query={encoded_name}+{urllib.parse.quote_plus(city_name)}"
            html_output += f'  <li><a href="{map_link}" target="_blank" rel="noopener noreferrer">{clean_name}</a></li>\n'
        html_output += "</ul>"
        return html_output
    except Exception as e:
        print(f"Lỗi khi lấy gợi ý địa điểm từ Gemini cho {city_name}: {e}")
        return f"Xin lỗi, tôi gặp sự cố khi tìm kiếm gợi ý địa điểm cho {city_name}."

def get_navigation_link_html(destination_place: str, city_context: str = "", user_lat: float = None, user_lon: float = None):
    """
    Tạo link Google Maps chỉ đường hoặc tìm kiếm và trả về dưới dạng HTML.
    """
    if not destination_place:
        return "Vui lòng cung cấp địa điểm bạn muốn đến."

    # Kết hợp destination_place và city_context để tìm kiếm chính xác hơn
    full_destination_query = destination_place
    if city_context and city_context.lower() not in destination_place.lower(): # Tránh lặp lại tên thành phố
        full_destination_query += f", {city_context}"
    
    encoded_destination = urllib.parse.quote_plus(full_destination_query)

    if user_lat is not None and user_lon is not None:
        # Tạo link chỉ đường từ vị trí người dùng đến đích
        # saddr (source address) có thể là lat,lon
        map_link = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={encoded_destination}"
        link_text = f"Chỉ đường đến {destination_place}"
        message = f"<p>Đang tạo chỉ đường từ vị trí của bạn đến <strong>{destination_place}</strong>...</p>"
    else:
        # Tạo link tìm kiếm địa điểm (không có chỉ đường từ vị trí cụ thể)
        map_link = f"https://www.google.com/maps/search/?api=1&query={encoded_destination}"
        link_text = f"Tìm {destination_place} trên bản đồ"
        message = f"<p>Không có thông tin vị trí của bạn. Nhấp vào đây để tìm <strong>{destination_place}</strong> trên bản đồ:</p>"
        if not (user_lat is None and user_lon is None): # Tức là có lỗi khi lấy tọa độ chứ không phải là không có
             message = f"<p>Không lấy được vị trí hiện tại của bạn. Nhấp vào đây để tìm <strong>{destination_place}</strong> trên bản đồ:</p>"


    html_output = f'{message}\n<p><a href="{map_link}" target="_blank" rel="noopener noreferrer" class="map-navigation-link">{link_text}</a></p>'
    if user_lat is None and user_lon is None: # Chỉ khi không có ý định lấy tọa độ
        html_output += "<p><small>Để có chỉ đường chính xác hơn, bạn có thể thử cho phép truy cập vị trí khi được hỏi.</small></p>"
    
    return html_output


@app.get("/ask")
async def ask_weather_agent(
    question: str,
    user_lat: float = Query(None, alias="latitude"), # Nhận latitude từ query param
    user_lon: float = Query(None, alias="longitude") # Nhận longitude từ query param
):
    global intent_details_holder
    if not question.strip():
        return {"message": "Vui lòng đặt câu hỏi hoặc nhập tên thành phố."}

    intent_details = analyze_user_intent_with_gemini(question)
    intent_details_holder["details"] = intent_details

    city = intent_details.get("city")
    place_name = intent_details.get("place_name") # Lấy tên địa điểm cụ thể
    intent = intent_details.get("intent")
    num_days = intent_details.get("num_days", 1)

    # print(f"Endpoint received: lat={user_lat}, lon={user_lon}") # Debug

    # Xử lý logic thiếu thông tin cơ bản
    if intent != "unknown" and intent != "specific_place_navigation" and not city: # Cần city cho các intent thời tiết, gợi ý chung
        prompt_extract_city_only = f"Trích xuất tên thành phố từ câu sau: \"{question}\". Chỉ trả về tên thành phố. Nếu không có, trả về 'Không tìm thấy'."
        response_city_only = gemini_model.generate_content(prompt_extract_city_only)
        extracted_city = response_city_only.text.strip()
        if extracted_city != "Không tìm thấy" and extracted_city:
            city = extracted_city
            intent_details["city"] = city
            intent_details_holder["details"]["city"] = city
        else:
             return {"message": "Xin lỗi, tôi không thể xác định tên thành phố từ câu hỏi của bạn để cung cấp thông tin. Vui lòng thử lại."}
    elif intent == "specific_place_navigation" and not place_name:
        return {"message": "Bạn muốn tôi tìm đường đến địa điểm cụ thể nào vậy?"}
    elif not city and not place_name and intent == "unknown":
         return {"message": "Xin lỗi, tôi chưa hiểu câu hỏi của bạn. Bạn có thể hỏi về thời tiết, gợi ý trang phục, địa điểm du lịch chung, hoặc đường đi đến một địa điểm cụ thể cho một thành phố không?"}


    # Xử lý các intent
    if intent == "current_weather":
        # ... (giữ nguyên)
        data, error = get_weather_data(city, weather_api_key, type="weather")
        if error: return {"message": error}
        response_text, _ = format_current_weather(data, city_name_override=city)
        return {"message": response_text}
    elif intent == "clothing_advice_today":
        # ... (giữ nguyên)
        data, error = get_weather_data(city, weather_api_key, type="weather")
        if error: return {"message": error}
        current_weather_text, weather_info = format_current_weather(data, city_name_override=city)
        if not weather_info: return {"message": f"Không có đủ thông tin thời tiết cho {city} để đưa ra lời khuyên."}
        advice = get_clothing_advice(weather_info, f"hôm nay tại {city}")
        return {"message": f"{current_weather_text}\n\n{advice}"}

    elif intent == "forecast_tomorrow" or (intent == "forecast_next_days" and num_days == 1):
        # ... (giữ nguyên)
        data, error = get_weather_data(city, weather_api_key, type="forecast")
        if error: return {"message": error}
        response_text, _ = format_daily_forecast(data, 1, city_name_override=city)
        return {"message": response_text}

    elif intent == "clothing_advice_tomorrow":
        # ... (giữ nguyên)
        data, error = get_weather_data(city, weather_api_key, type="forecast")
        if error: return {"message": error}
        forecast_text, weather_info_tomorrow = format_daily_forecast(data, 1, city_name_override=city)
        if not weather_info_tomorrow:
            if "Không có dữ liệu dự báo" in forecast_text or "chưa có đủ dữ liệu" in forecast_text:
                 return {"message": forecast_text}
            return {"message": f"Không có đủ thông tin thời tiết cho ngày mai tại {city} để đưa ra lời khuyên."}
        advice = get_clothing_advice(weather_info_tomorrow, f"ngày mai tại {city}")
        return {"message": f"{forecast_text}\n\n{advice}"}

    elif intent == "forecast_next_days":
        # ... (giữ nguyên)
        clamped_num_days = max(1, min(num_days, 5))
        data, error = get_weather_data(city, weather_api_key, type="forecast")
        if error: return {"message": error}
        response_text, _ = format_daily_forecast(data, clamped_num_days, city_name_override=city)
        return {"message": response_text}
    
    elif intent == "place_recommendation":
        if not city:
            return {"message": "Bạn muốn tôi gợi ý địa điểm ở thành phố nào vậy?"}
        recommendations_html = get_place_recommendations_from_gemini(city)
        return {"message": recommendations_html}
    
    elif intent == "specific_place_navigation":
        if not place_name: # Đã kiểm tra ở trên, nhưng thêm an toàn
            return {"message": "Bạn muốn tìm đường đến địa điểm nào?"}
        # city có thể rỗng nếu place_name đã đủ rõ (VD: "Sân bay Nội Bài")
        # hoặc city được trích xuất từ place_name.
        navigation_html = get_navigation_link_html(place_name, city_context=city, user_lat=user_lat, user_lon=user_lon)
        return {"message": navigation_html}
        
    elif intent == "unknown":
        # ... (logic hiện tại có thể giữ nguyên hoặcปรับปรุง)
        if city or place_name: # Nếu có thông tin nào đó
            default_info = ""
            if city and not place_name: # Ưu tiên thời tiết nếu chỉ có city
                data, error = get_weather_data(city, weather_api_key, type="weather")
                if not error:
                    default_info, _ = format_current_weather(data, city_name_override=city)

            clarification_context = f"Người dùng đã hỏi: \"{question}\"."
            if default_info:
                clarification_context += f" Tôi đã cung cấp thông tin: \"{default_info}\"."
            
            clarification_prompt = f"""{clarification_context}
            Hãy hỏi người dùng một cách thân thiện xem họ muốn biết cụ thể thông tin gì khác không (ví dụ: dự báo, mặc gì, địa điểm tham quan, đường đi tới một nơi cụ thể).
            Câu trả lời của bạn:"""
            try:
                clarification_response = gemini_model.generate_content(clarification_prompt)
                final_message = (default_info + "\n\n" if default_info else "") + clarification_response.text.strip()
                return {"message": final_message}
            except Exception:
                 return {"message": (default_info + "\n\n" if default_info else "") + "Bạn có muốn biết thêm thông tin gì khác không?"}
        else: # Hoàn toàn không có thông tin city hay place
            return {"message": "Xin lỗi, tôi chưa hiểu rõ câu hỏi của bạn. Bạn có thể cung cấp tên thành phố, địa điểm và yêu cầu cụ thể hơn không?"}
            
    else: # Các trường hợp intent khác chưa xử lý (nếu có)
        return {"message": "Xin lỗi, tôi chưa hiểu yêu cầu của bạn. Tôi có thể giúp bạn về thời tiết, trang phục, gợi ý địa điểm hoặc chỉ đường."}