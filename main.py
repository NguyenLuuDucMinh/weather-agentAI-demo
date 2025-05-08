import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from dotenv import load_dotenv
import google.generativeai as genai # Thư viện mới cho Gemini

# Load biến môi trường
load_dotenv()
google_ai_api_key = os.getenv("GOOGLE_AI_API_KEY")
weather_api_key = os.getenv("OPENWEATHERMAP_API_KEY")

# Khởi tạo Google Generative AI client
if not google_ai_api_key:
    print("Lỗi: GOOGLE_AI_API_KEY chưa được thiết lập trong file .env")
    exit()
if not weather_api_key:
    print("Lỗi: OPENWEATHERMAP_API_KEY chưa được thiết lập trong file .env")
    exit()

genai.configure(api_key=google_ai_api_key)
# Chọn model, ví dụ 'gemini-pro' cho các tác vụ text generation
# Hoặc 'gemini-1.5-flash-latest' cho tốc độ nhanh hơn và chi phí có thể tối ưu hơn
# gemini_model = genai.GenerativeModel('gemini-pro')
gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')


# FastAPI app setup
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ask")
def ask_ai(question: str):
    if not question.strip():
        return {"message": "Vui lòng đặt câu hỏi hoặc nhập tên thành phố."}

    # Gọi Gemini để trích xuất tên thành phố
    try:
        prompt_extract_city = f"""
        Bạn là một trợ lý AI. Nhiệm vụ của bạn là trích xuất CHÍNH XÁC tên thành phố từ câu hỏi của người dùng.
        Chỉ trả về tên thành phố. Nếu không có tên thành phố nào trong câu hỏi, hãy trả về một chuỗi rỗng.
        Câu hỏi: "{question}"
        Tên thành phố:
        """
        response = gemini_model.generate_content(prompt_extract_city)
        city = response.text.strip()
        # print(f"Gemini extracted city: '{city}'") # Gỡ lỗi
    except Exception as e:
        print(f"Google Gemini city extraction error: {e}") # Gỡ lỗi
        # Kiểm tra các lỗi cụ thể của Google API nếu cần, ví dụ:
        # from google.api_core import exceptions as google_exceptions
        # if isinstance(e, google_exceptions.PermissionDenied):
        # return {"message": "Lỗi xác thực với Google AI. Vui lòng kiểm tra API key."}
        # elif isinstance(e, google_exceptions.ResourceExhausted):
        # return {"message": "Đã hết quota sử dụng Google AI. Vui lòng kiểm tra tài khoản Google AI Studio."}
        return {"message": "Xin lỗi, tôi gặp sự cố khi phân tích câu hỏi của bạn với Gemini."}

    if not city:
        return {"message": "Xin lỗi, tôi không thể xác định tên thành phố từ câu hỏi của bạn. Vui lòng thử lại với tên thành phố cụ thể."}

    # Gọi API thời tiết OpenWeatherMap
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={weather_api_key}&units=metric&lang=vi"
    
    try:
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()

        main_data = data.get("main")
        weather_list = data.get("weather")

        if not main_data or not weather_list or not weather_list[0]:
            return {"message": f"Xin lỗi, dữ liệu thời tiết nhận được cho {city} không đầy đủ."}

        temp = main_data.get("temp")
        desc = weather_list[0].get("description")
        city_name_from_api = data.get("name", city)

        if temp is None or desc is None:
            return {"message": f"Xin lỗi, không thể lấy thông tin nhiệt độ hoặc mô tả thời tiết chi tiết cho {city_name_from_api}."}

        # Tạo câu trả lời tự nhiên từ Gemini
        prompt_natural_answer = f"""
        Bạn là trợ lý AI thân thiện chuyên báo thời tiết. Hãy trả lời một cách tự nhiên, ngắn gọn và dễ hiểu.
        Thông tin thời tiết:Xin chao bạn! Thời tiết hiện tại ở {city_name_from_api} có {desc}, nhiệt độ khoảng {temp}°C.Chúc bạn một ngày tốt lành!
        Hãy nhớ rằng thông tin thời tiết có thể thay đổi nhanh chóng, vì vậy hãy kiểm tra thường xuyên để cập nhật thông tin mới nhất.
        Câu trả lời của bạn:
        """
        
        final_response = gemini_model.generate_content(prompt_natural_answer)
        answer = final_response.text.strip()
        # print(f"Gemini natural answer: '{answer}'") # Gỡ lỗi
        return {"message": answer}

    except requests.exceptions.HTTPError as http_err:
        if r.status_code == 404:
            return {"message": f"Xin lỗi, tôi không tìm thấy thông tin thời tiết cho thành phố '{city}'. Vui lòng kiểm tra lại tên thành phố."}
        elif r.status_code == 401:
            return {"message": "Lỗi xác thực với dịch vụ thời tiết. Có thể API key của OpenWeatherMap không hợp lệ."}
        else:
            return {"message": f"Đã xảy ra lỗi ({r.status_code}) khi cố gắng lấy thông tin thời tiết cho '{city}'."}
    except requests.exceptions.RequestException:
        return {"message": "Lỗi kết nối đến dịch vụ thời tiết. Vui lòng kiểm tra kết nối mạng và thử lại."}
    except KeyError:
        return {"message": f"Xin lỗi, có lỗi xảy ra khi xử lý dữ liệu thời tiết nhận được cho {city}."}
    except Exception as e:
        print(f"An unexpected error occurred (after weather API or during Gemini final response): {e}") # Gỡ lỗi
        return {"message": "Xin lỗi, tôi đã gặp một lỗi không mong muốn. Vui lòng thử lại sau."}

# Để chạy server: uvicorn main:app --reload