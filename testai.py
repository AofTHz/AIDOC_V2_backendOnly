from google import genai, generativeai
import os

os.environ["GOOGLE_API_KEY"] = "AIzaSyCvBQuefC2a9kOsOSd4zDqYmttZIi2O0Y4"
generativeai.configure(api_key="AIzaSyCvBQuefC2a9kOsOSd4zDqYmttZIi2O0Y4")
client = genai.Client()

for model_info in client.models.list():
    print(model_info.name)

response = client.models.generate_content(
    model=f"tunedModels/pdf-tuned-model4",
    contents="โครงงาน การจำแนกประเภทเอกสารด้วยเจเนอเรทีฟ เอไอ เป็นโครงงานที่จัดทำเพื่อศึกษาค้นคว้าการนำ AI มาประยุกต์ใช้งานในชีวิตประจำวัน เป็นเว็บแอพพลิเคชั่นที่สามารถช่วยคัดแยกไฟล์PDF จำนวนหนึ่งหรือจำนวนมากได้ โดยออกแบบมาให้แยก ต่อผู้ใช้งาน เพื่อความสะดวกในการแยกไฟล์และปรับแต่งความต้องการส่วนบุคคล และ เครื่องมือชิ้นนี้จะเป็นกรณีศึกษาชั้นดีในการนำ AI มาประยุกต์ใช้งานในเรื่องต่างๆ และเตรียมปรับตัวเข้าสู่เทคโนโลยีAI ในอนาคตที่จะมาถึงข้างหน้านี้ผลการพัฒนาเว็บไซต์แอพพลิเคชั่นนี้ โดยหลังจากพัฒนาเสร็จแล้ว เว็บไซต์จะสามารถใช้งานสำหรับในส่วนของแค่การวัด ประสิทธิภาพ ความแม่นยำ และผลการปรับแต่ง Gemini AIและอื่นๆเป็นต้น"
)

print(response.text)
